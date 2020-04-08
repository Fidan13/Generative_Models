import tensorflow as tf
from keras_radam import RAdam
from graphs.regularized.DIP_AE_graph import create_DIP_Bayesian_losses
from evaluation.quantitive_metrics.metrics import create_metrics
from training.autoencoding_basic.autoencoders.autoencoder import autoencoder as basicAE
from training.regularized.DIP_shared import regularize
import tensorflow_probability as tfp

class DIP_BayesianCovariance_AE(basicAE):
    # override function
    def compile(
            self,
            optimizer=RAdam(),
            loss=None,
            **kwargs
    ):

        ae_losses = create_DIP_Bayesian_losses()
        loss = loss or {}
        for k in loss:
            ae_losses.pop(k)
        self.ae_losses = {**ae_losses, **loss}

        if 'metrics' in kwargs.keys():
            self.ae_metrics = kwargs.pop('metrics', None)
        else:
            self.ae_metrics = create_metrics([self.batch_size] + self.get_inputs_shape()[-3:])

        tf.keras.Model.compile(self, optimizer=optimizer, loss=self.ae_losses, metrics=self.ae_metrics, **kwargs)
        print(self.summary())

    def __encode__(self, **kwargs):
        inputs = kwargs['inputs']
        for k, v in  inputs.items():
            if inputs[k].shape == self.get_inputs_shape():
                inputs[k] = tf.reshape(inputs[k], (1, ) + self.get_inputs_shape())
            inputs[k] = tf.cast(inputs[k], tf.float32)
        kwargs['model']  = self.get_variable
        kwargs['latents_shape'] = (self.batch_size, self.latents_dim)

        encoded = self.encode_fn(**kwargs)
        covariance_mean, covariance_regularizer = regularize(latent_mean=encoded['z_latents'], \
                                                       regularize=True, lambda_d=self.lambda_d, d=self.lambda_od)

        covariance_logvariance = tf.sigmoid(encoded['z_latents'])
        covariance_sigma = tf.reduce_mean(tf.linalg.diag(tf.exp(covariance_logvariance)), axis=0)
        prior_distribution = tfp.distributions.Normal(loc=covariance_mean, scale=covariance_sigma)
        posterior_distribution = tfp.distributions.Normal(loc=encoded['z_latents'], scale=covariance_sigma)
        bayesian_divergent = tfp.distributions.kl_divergence(posterior_distribution, prior_distribution, \
                                                                 name='bayesian_divergent')

        return {**encoded, 'covariance_regularized': covariance_regularizer, 'bayesian_divergent': bayesian_divergent}

    def __init_autoencoder__(self, **kwargs):
        #  DIP configuration
        self.lambda_d = 100
        self.lambda_od = 50

        # connect the graph x' = decode(encode(x))
        inputs_dict= {k: v.inputs[0] for k, v in self.get_variables().items() if k == 'inference'}
        encoded = self.__encode__(inputs=inputs_dict)
        x_logits = self.decode(latents={'z_latents': encoded['z_latents']})
        covariance_mean = encoded['covariance_mean']
        covariance_regularizer =  encoded['covariance_regularized']
        bayesian_divergent = encoded['bayesian_divergent']

        outputs_dict = {
            'x_logits': x_logits,
            'covariance_regularized': covariance_regularizer,
            'covariance_mean': covariance_mean,
            'bayesian_divergent': bayesian_divergent
        }
        tf.keras.Model.__init__(
            self,
            name=self.name,
            inputs=inputs_dict,
            outputs=outputs_dict,
            **kwargs
        )

    def __rename_outputs__(self):
        # rename the outputs
        ## rename the outputs
        for i, output_name in enumerate(self.output_names):
            if 'x_logits' in output_name:
                self.output_names[i] = 'x_logits'
            elif 'covariance_regularized' in output_name:
                self.output_names[i] = 'covariance_regularized'
            elif 'bayesian_divergent' in output_name:
                self.output_names[i] = 'bayesian_divergent'
            else:
                print(self.output_names[i])

    def batch_cast(self, batch):
        if self.input_kw:
            x = tf.cast(batch[self.input_kw], dtype=tf.float32)/self.input_scale
        else:
            x = tf.cast(batch, dtype=tf.float32)/self.input_scale

        return {
                   'inference_inputs': x,
               }, \
               {
                   'x_logits': x,
                   'covariance_regularized': 0.0,
                   'bayesian_divergent': 0.0
               }

