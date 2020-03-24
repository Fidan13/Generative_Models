import os

import tensorflow as tf
from keras_radam import RAdam

from evaluation.quantitive_metrics.metrics import create_metrics
from graphs.basics.AE_graph import create_graph, create_losses, encode_fn, decode_fn, generate_sample
from graphs.builder import load_models, save_models


class autoencoder(tf.keras.Model):
    def __init__(
            self,
            name,
            inputs_shape,
            outputs_shape,
            latent_dim,
            variables_params,
            batch_size=100,
            filepath=None,
            model_fn=create_graph,
            encode_fn=encode_fn,
            **kwargs
    ):
        self.get_variables = model_fn(
            name=name,
            variables_params=variables_params,
            restore=filepath
        )
        self.filepath = filepath
        self._name = name
        self.inputs_shape = inputs_shape
        self.outputs_shape = outputs_shape
        self.latent_dim = latent_dim
        self.batch_size = batch_size
        self.encode_fn = encode_fn
        self.decode_fn = decode_fn
        self.generate_sample = generate_sample
        self.save_models = save_models
        self.load_models = load_models
        self.connect(**kwargs)
        self.outputs_renaming_fn()

    def connect(self, **kwargs):
        # connect the graph x' = decode(encode(x))
        inputs_dict= {k: v.inputs[0] for k, v in self.get_variables().items() if k == 'inference'}
        latent = self.encode(inputs=inputs_dict)
        x_logits = self.decode(latent)
        outputs_dict =  [x_logits]

        tf.keras.Model.__init__(
            self,
            name=self.name,
            inputs=inputs_dict,
            outputs=outputs_dict,
            **kwargs
        )

    def outputs_renaming_fn(self):
        # rename the outputs
        self.output_names = ['x_logits']

    def compile(
            self,
            optimizer=RAdam(),
            loss=None,
            metrics=create_metrics(),
            **kwargs
    ):
        self.ae_losses = create_losses()
        loss = loss or {}
        model_losses = {**self.ae_losses, **loss}
        self.ae_metrics = metrics
        tf.keras.Model.compile(self, optimizer=optimizer, loss=model_losses, metrics=metrics, **kwargs)
        print(self.summary())

    def fit(
            self,
            x,
            y=None,
            input_kw='image',
            input_scale=1.0,
            steps_per_epoch=None,
            epochs=1,
            verbose=1,
            callbacks=None,
            validation_data=None,
            validation_steps=None,
            validation_freq=1,
            class_weight=None,
            max_queue_size=10,
            workers=1,
            use_multiprocessing=False,
            shuffle=True,
            initial_epoch=0
    ):
        self.input_kw = input_kw
        self.input_scale = input_scale
        return \
            tf.keras.Model.fit(
                self,
                x=x.map(self.batch_cast),
                y=y,
                steps_per_epoch=steps_per_epoch,
                epochs=epochs,
                verbose=verbose,
                callbacks=callbacks,
                validation_data=None if validation_data is None else validation_data.map(self.batch_cast),
                validation_steps=validation_steps,
                validation_freq=validation_freq,
                class_weight=class_weight,
                max_queue_size=max_queue_size,
                workers=workers,
                use_multiprocessing=use_multiprocessing,
                shuffle=shuffle,
                initial_epoch=initial_epoch
            )

    def encode(self, **kwargs):
        inputs = kwargs['inputs']
        for k, v in  inputs.items():
            if inputs[k].shape == self.inputs_shape:
                inputs[k] = tf.reshape(inputs[k], (1, ) + self.inputs_shape)
            inputs[k] = tf.cast(inputs[k], tf.float32)
        kwargs['model']  = self.get_variable
        kwargs['latent_shape'] = (self.batch_size, self.latent_dim)
        return self.encode_fn(**kwargs)

    def decode(self, latent):
        return self.decode_fn(model=self.get_variable, latent=latent, inputs_shape=self.inputs_shape)

    def get_variable(self, var_name, param):
        return self.get_variables()[var_name](*param)

    def save(self,
             filepath,
             overwrite=True,
             include_optimizer=True,
             save_format=None,
             signatures=None,
             options=None):
        file_Name = os.path.join(filepath, self.name)
        self.save_models(file_Name, self.get_variables())

    def batch_cast(self, batch):
        if self.input_kw:
            x = tf.cast(batch[self.input_kw], dtype=tf.float32)/self.input_scale
        else:
            x = tf.cast(batch, dtype=tf.float32)/self.input_scale

        return {
                   'inference_inputs': x,
               }, \
               {
                   'x_logits': x
               }
