from graphs.adversarial.AAE_graph import inputs_discriminate_encode_fn
import tensorflow as tf
from training.callbacks.early_stopping import EarlyStopping
from training.autoencoding_basic.transformative.AE import autoencoder
from utils.swe.codes import copy_fn

class AAE(autoencoder):
    def __init__(
            self,
            adversarial_losses,
            strategy=None,
            **kwargs
    ):
        self.strategy = strategy
        autoencoder.__init__(
            self,
            **kwargs
        )
        self.ONES = tf.ones(shape=[self.batch_size, 1])
        self.ZEROS = tf.zeros(shape=[self.batch_size, 1])

    def get_discriminators(self):
        return {
            'inputs_discriminator_real': self.inputs_discriminator_real,
            'inputs_discriminator_fake': self.inputs_discriminator_fake,
            'inputs_generator_fake': self.inputs_generator_fake
        }

    def inputs_discriminator_real_batch_cast(self, xt0, xt1):
        xt0 = tf.cast(xt0, dtype=tf.float32) / self.input_scale
        xt1 = tf.cast(xt1, dtype=tf.float32) / self.input_scale

        en = autoencoder.encode(self, inputs={'inputs': xt0})
        return {'generative_inputs': en['z_latent'],
                'inputs_discriminator_real_inputs': en['z_latent']
                } ,\
               {
                   'inputs_discriminator_real_outputs': self.ONES
               }

    def inputs_discriminator_fake_batch_cast(self, xt0, xt1):
        xt0 = tf.cast(xt0, dtype=tf.float32) / self.input_scale
        xt1 = tf.cast(xt1, dtype=tf.float32) / self.input_scale

        en = autoencoder.encode(self, inputs={'inputs': xt0})
        return {'generative_inputs': en['z_latent'],
                'inputs_discriminator_fake_inputs': en['z_latent']
                } ,\
               {
                   'inputs_discriminator_fake_outputs': self.ZEROS
               }

    def inputs_generator_fake_batch_cast(self, xt0, xt1):
        xt0 = tf.cast(xt0, dtype=tf.float32) / self.input_scale
        xt1 = tf.cast(xt1, dtype=tf.float32) / self.input_scale

        en = autoencoder.encode(self, inputs={'inputs': xt0})
        return {'generative_inputs': en['z_latent'],
                'inputs_generator_fake_inputs': en['z_latent']
                } ,\
               {
                   'inputs_generator_fake_outputs': self.ONES
               }

    def together_batch_cast(self,  xt0, xt1):
        xt0 = tf.cast(xt0, dtype=tf.float32) / self.input_scale
        xt1 = tf.cast(xt1, dtype=tf.float32) / self.input_scale

        en = autoencoder.encode(self, inputs={'inputs': xt0})
        return {   'inference_inputs': xt0,
                   'generative_inputs': en['z_latent']} ,\
               {
                   'x_logits': xt1,
                   'inputs_discriminator_real_outputs': self.ONES ,
                   'inputs_discriminator_fake_outputs': self.ZEROS,
                   'inputs_generator_fake_outputs': self.ONES
               }

    def compile(
            self,
            adversarial_losses,
            adversarial_weights,
            **kwargs
    ):
        self.adversarial_losses=adversarial_losses
        self.adversarial_weights=adversarial_weights
        autoencoder.compile(
            self,
            **kwargs
        )

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
        print()
        print('training basic basicAE')
        # 1- train the basic basicAE
        autoencoder.fit(
            self,
            x=x,
            y=y,
            input_kw=input_kw,
            input_scale=input_scale,
            steps_per_epoch=steps_per_epoch,
            epochs=epochs,
            verbose=verbose,
            callbacks=callbacks,
            validation_data=validation_data,
            validation_steps=validation_steps,
            validation_freq=validation_freq,
            class_weight=class_weight,
            max_queue_size=max_queue_size,
            workers=workers,
            use_multiprocessing=use_multiprocessing,
            shuffle=shuffle,
            initial_epoch=initial_epoch
        )

        def create_inputs_discriminator():
            for k, var in self.get_variables().items():
                for layer in var.layers:
                    if not isinstance(layer, tf.keras.layers.Activation):
                        if hasattr(layer, 'activation'):
                            layer.activation = tf.keras.activations.elu

            temp_layers = tf.keras.models.clone_model(self.get_variables()['generative']).layers
            temp_layers.append(tf.keras.layers.Flatten())
            temp_layers.append(tf.keras.layers.Dense(units=1, activation='linear', name='inputs_discriminator_real_outputs'))
            temp_layers = tf.keras.Sequential(temp_layers)
            self.inputs_discriminator_real = tf.keras.Model(
                name='inputs_discriminator_real',
                inputs=temp_layers.inputs,
                outputs=temp_layers.outputs
            )

            temp_layers = tf.keras.models.clone_model(self.get_variables()['generative']).layers
            temp_layers.append(tf.keras.layers.Flatten())
            temp_layers.append(tf.keras.layers.Dense(units=1, activation='linear', name='inputs_discriminator_fake_outputs'))
            temp_layers = tf.keras.Sequential(temp_layers)
            self.inputs_discriminator_fake = tf.keras.Model(
                name='inputs_discriminator_fake',
                inputs=temp_layers.inputs,
                outputs=temp_layers.outputs
            )

            temp_layers = tf.keras.models.clone_model(self.get_variables()['generative']).layers
            temp_layers.append(tf.keras.layers.Flatten())
            temp_layers.append(tf.keras.layers.Dense(units=1, activation='linear', name='inputs_generator_fake_outputs'))
            temp_layers = tf.keras.Sequential(temp_layers)
            self.inputs_generator_fake = tf.keras.Model(
                name='inputs_generator_fake',
                inputs=temp_layers.inputs,
                outputs=temp_layers.outputs
            )

        # 2- create inputs discriminator
        if self.strategy:
            with self.strategy:
                create_inputs_discriminator()
        else:
            create_inputs_discriminator()

        # 3- clone autoencoder variables
        self.ae_get_variables = copy_fn(self.get_variables)

        # 4- switch to discriminate
        if self.strategy:
            if self.strategy:
                self.inputs_discriminator_compile()
        else:
            self.inputs_discriminator_compile()

        print()
        print('training inputs real discriminator')
        # 5- train the inputs discriminator
        self.inputs_discriminator_real.fit(
            x=x.map(self.inputs_discriminator_real_batch_cast),
            y=y,
            steps_per_epoch=steps_per_epoch,
            epochs=epochs,
            verbose=1,
            callbacks=[EarlyStopping()],
            validation_data=validation_data.map(self.inputs_discriminator_real_batch_cast),
            validation_steps=validation_steps,
            validation_freq=validation_freq,
            class_weight=class_weight,
            max_queue_size=max_queue_size,
            workers=workers,
            use_multiprocessing=use_multiprocessing,
            shuffle=shuffle,
            initial_epoch=initial_epoch
        )

        print()
        print('training inputs fake discriminator')
        self.inputs_discriminator_fake.fit(
            x=x.map(self.inputs_discriminator_fake_batch_cast),
            y=y,
            steps_per_epoch=steps_per_epoch,
            epochs=epochs,
            verbose=1,
            callbacks=[EarlyStopping()],
            validation_data=validation_data.map(self.inputs_discriminator_fake_batch_cast),
            validation_steps=validation_steps,
            validation_freq=validation_freq,
            class_weight=class_weight,
            max_queue_size=max_queue_size,
            workers=workers,
            use_multiprocessing=use_multiprocessing,
            shuffle=shuffle,
            initial_epoch=initial_epoch
        )

        print()
        print('training inputs fake generator')
        self.inputs_generator_fake.fit(
            x=x.map(self.inputs_generator_fake_batch_cast),
            y=y,
            steps_per_epoch=steps_per_epoch,
            epochs=epochs,
            verbose=1,
            callbacks=[EarlyStopping()],
            validation_data=validation_data.map(self.inputs_generator_fake_batch_cast),
            validation_steps=validation_steps,
            validation_freq=validation_freq,
            class_weight=class_weight,
            max_queue_size=max_queue_size,
            workers=workers,
            use_multiprocessing=use_multiprocessing,
            shuffle=shuffle,
            initial_epoch=initial_epoch
        )


        # 6- connect all for inputs_adversarial training
        if self.strategy:
            if self.strategy:
                self.connect_together()
        else:
            self.connect_together()

        print()
        print('training together')
        cbs = [cb for cb in callbacks or [] if isinstance(cb, tf.keras.callbacks.CSVLogger)]
        for cb in cbs:
            cb.filename = cb.filename.split('.csv')[0] + '_together.csv'
            mertic_names = [fn for sublist in [[k + '_' + fn.__name__ for fn in v] for k, v in self.ae_metrics.items()]
                            for fn in sublist]
            cb.keys = ['loss'] + [fn+'_loss' for fn in self._AA.output_names] + mertic_names
            cb.append_header = cb.keys

        # 7- training together
        self._AA.fit(
            x=x.map(self.together_batch_cast),
            y=y,
            steps_per_epoch=steps_per_epoch,
            epochs=epochs,
            verbose=0,
            callbacks=callbacks,
            validation_data=validation_data.map(self.together_batch_cast),
            validation_steps=validation_steps,
            validation_freq=validation_freq,
            class_weight=class_weight,
            max_queue_size=max_queue_size,
            workers=workers,
            use_multiprocessing=use_multiprocessing,
            shuffle=shuffle,
            initial_epoch=initial_epoch
        )


    def connect_together(self):
        self.get_variables = self.adversarial_get_variables
        self.encode_fn = inputs_discriminate_encode_fn
        _inputs = {
            'inputs': self.get_variables()['inference'].inputs[0]
        }
        encoded = self.encode(inputs=_inputs)
        x_logits = self.decode(encoded['z_latent'])

        _outputs = {
            'x_logits': x_logits,
            'inputs_discriminator_real_pred': encoded['inputs_discriminator_real_pred'],
            'inputs_discriminator_fake_pred': encoded['inputs_discriminator_fake_pred'],
            'inputs_generator_fake_pred': encoded['inputs_generator_fake_pred']
        }
        self._AA = tf.keras.Model(
            name='inputs_AA',
            inputs= _inputs,
            outputs=_outputs
        )

        for i, _output in enumerate(self._AA.output_names):
            if 'tf_op_layer_x_logits' in _output :
                self._AA.output_names[i] = 'x_logits'
            elif 'inputs_discriminator_fake' in _output :
                self._AA.output_names[i] = 'inputs_discriminator_fake_outputs'
            elif 'inputs_generator_fake' in _output :
                self._AA.output_names[i] = 'inputs_generator_fake_outputs'
            elif 'inputs_discriminator_real' in _output :
                self._AA.output_names[i] = 'inputs_discriminator_real_outputs'
            else:
                pass

        generator_weight = self.adversarial_weights['generator_weight']
        discriminator_weight = self.adversarial_weights['discriminator_weight']
        generator_losses = [k for k in self.adversarial_losses.keys() if 'generator' in k]
        glen = len(self.ae_losses)+len(generator_losses)
        dlen = len(self.adversarial_losses)-len(generator_losses)
        aeloss_weights = {k: (1-generator_weight)/glen for k in self.ae_losses.keys()}
        gloss_weights = {k: generator_weight/glen for k in generator_losses}
        discriminator_weights = {k: (1 - discriminator_weight)/dlen for k in self.adversarial_losses.keys() if k not in generator_losses}
        self._AA.compile(
            optimizer=self.optimizer,
            loss={**self.ae_losses, **self.adversarial_losses},
            metrics=self.ae_metrics,
            loss_weights={**aeloss_weights, **gloss_weights, **discriminator_weights}
        )

        self._AA.generate_sample = self.generate_sample
        self._AA.get_varibale = self.get_varibale
        self._AA.inputs_shape = self.inputs_shape
        self._AA.latent_dim = self.latent_dim

        print(self._AA.summary())


    def inputs_discriminator_compile(self, **kwargs):
        self.inputs_discriminator_real.compile(
            optimizer=self.optimizer,
            loss=self.adversarial_losses['inputs_discriminator_real_outputs'](),
            metrics=None
        )

        print(self.inputs_discriminator_real.summary())

        self.inputs_discriminator_fake.compile(
            optimizer=self.optimizer,
            loss=self.adversarial_losses['inputs_discriminator_fake_outputs'](),
            metrics=None
        )

        print(self.inputs_discriminator_fake.summary())

        self.inputs_generator_fake.compile(
            optimizer=self.optimizer,
            loss=self.adversarial_losses['inputs_generator_fake_outputs'](),
            metrics=None
        )

        print(self.inputs_generator_fake.summary())

    # combined models special
    def adversarial_get_variables(self):
        return {**self.ae_get_variables(), **self.get_discriminators()}
