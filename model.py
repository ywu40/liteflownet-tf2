from warp import *
import tensorflow as tf
import tensorflow_addons as tfa


class LiteFlowNet():
    def __init__(self):
        self.dblBackward = [0.0, 0.0, 10.0, 5.0, 2.5, 1.25, 0.625]

    def feature_extractor(self):
        lrelu = lambda x: tf.nn.leaky_relu(x, 0.1)

        # module one
        m1 = tf.keras.Sequential()
        m1.add(tf.keras.layers.Conv2D(filters=32, kernel_size=7,  activation=lrelu, padding='SAME'))

        # module two
        m2 = tf.keras.Sequential()
        m2.add(tf.keras.layers.ZeroPadding2D(padding=(1, 1)))
        m2.add(tf.keras.layers.Conv2D(filters=32, kernel_size=3, strides=2,  activation=lrelu, padding='valid'))
        m2.add(tf.keras.layers.Conv2D(filters=32, kernel_size=3, activation=lrelu, padding='SAME'))
        m2.add(tf.keras.layers.Conv2D(filters=32, kernel_size=3, activation=lrelu, padding='SAME'))

        # module three
        m3 = tf.keras.Sequential()
        m3.add(tf.keras.layers.ZeroPadding2D(padding=(1, 1)))
        m3.add(tf.keras.layers.Conv2D(filters=64, kernel_size=3, strides=2, activation=lrelu, padding='valid'))
        m3.add(tf.keras.layers.Conv2D(filters=64, kernel_size=3, activation=lrelu,  padding='SAME'))

        # module four
        m4 = tf.keras.Sequential()
        m4.add(tf.keras.layers.ZeroPadding2D(padding=(1, 1)))
        m4.add(tf.keras.layers.Conv2D(filters=96, kernel_size=3, strides=2, activation=lrelu, padding='valid'))
        m4.add(tf.keras.layers.Conv2D(filters=96, kernel_size=3, activation=lrelu, padding='SAME'))

        # module five
        m5 = tf.keras.Sequential()
        m5.add(tf.keras.layers.ZeroPadding2D(padding=(1, 1)))
        m5.add(tf.keras.layers.Conv2D(filters=128, kernel_size=3, strides=2, activation=lrelu, padding='valid'))

        # module six
        m6 = tf.keras.Sequential()
        m6.add(tf.keras.layers.ZeroPadding2D(padding=(1, 1)))
        m6.add(tf.keras.layers.Conv2D(filters=192, kernel_size=3, strides=2, activation=lrelu, padding='valid'))

        return [m1, m2, m3, m4, m5, m6]

    def group_upconv(self, in1, groups, name):
        # keras don't have an easy way of group conv so use old way
        with tf.compat.v1.variable_scope('flownet'):
            with tf.compat.v1.variable_scope(name):
                filterc = tf.compat.v1.get_variable('filter_w', shape=[4, 4, 1, groups], dtype=tf.float32)
                shp = tf.shape(in1)
                output_shape = (shp[0], shp[1] * 2, shp[2] * 2, shp[3])
                return tf.nn.conv2d_transpose(in1, filterc, output_shape, strides=[1, 2, 2, 1])

    def matching(self, tensor_features1, tensor_features2, tensorFlow, int_level, name):
        with tf.name_scope(name):
            lrelu = lambda x: tf.nn.leaky_relu(x, 0.1)

            def module_feat():
                if int_level == 2:
                    return tf.keras.layers.Conv2D(filters=64, kernel_size=1, activation=lrelu, padding='valid')
                else:
                    return tf.keras.Sequential()

            def module_upcorr(x):
                return self.group_upconv(x, 49, name + '/moduleUpcorr')

            def module_upflow(x):
                return self.group_upconv(x, 2, name + '/moduleUpflow')

            def module_main(x):
                kernel_size = [1, 1, 7, 5, 5, 3, 3][int_level]
                with tf.name_scope("module_main"):
                    x = tf.keras.layers.Conv2D(filters=128, kernel_size=3, activation=lrelu, padding='SAME')(x)
                    x = tf.keras.layers.Conv2D(filters=64, kernel_size=3, activation=lrelu, padding='SAME')(x)
                    x = tf.keras.layers.Conv2D(filters=32, kernel_size=3, activation=lrelu, padding='SAME')(x)
                    x = tf.keras.layers.Conv2D(filters=2, kernel_size=kernel_size, activation=None, padding='SAME')(x)
                    return x

            with tf.name_scope('module_feat'):
                m_feat = module_feat()
                tensor_features1 = m_feat(tensor_features1)
                tensor_features2 = m_feat(tensor_features2)

            if tensorFlow is not None:
                tensorFlow = module_upflow(tensorFlow)
                # warp features
                tensor_features2 = tf_warp(tensor_features2, tensorFlow * self.dblBackward[int_level])

            if int_level >= 4:
                corr = tfa.layers.optical_flow.CorrelationCost(1, 3, 1, 1, 3, 'channels_last')([tensor_features1, tensor_features2])
                corr = lrelu(corr)
            else:
                corr = tfa.layers.optical_flow.CorrelationCost(1, 6, 2, 2, 6, 'channels_last')([tensor_features1, tensor_features2])
                corr = lrelu(module_upcorr(corr))

            # hack cuz corr cost lost last dimension
            corr.set_shape([None, None, None, 49])

            return (tensorFlow if tensorFlow is not None else 0.0) + module_main(corr)

    def subpixel(self, tensor_features1, tensor_features2, tensorFlow, int_level, name='subpixel'):
        with tf.name_scope(name):
            lrelu = lambda x: tf.nn.leaky_relu(x, 0.1)

            def module_feat():
                if int_level == 2:
                    return tf.keras.layers.Conv2D(filters=64, kernel_size=1, activation=lrelu, padding='valid')
                else:
                    return tf.keras.Sequential()

            def module_main(x):
                kernel_size = [1, 1, 7, 5, 5, 3, 3][int_level]
                with tf.name_scope("module_main"):
                    x = tf.keras.layers.Conv2D(filters=128, kernel_size=3, activation=lrelu, padding='SAME')(x)
                    x = tf.keras.layers.Conv2D(filters=64, kernel_size=3, activation=lrelu, padding='SAME')(x)
                    x = tf.keras.layers.Conv2D(filters=32, kernel_size=3, activation=lrelu, padding='SAME')(x)
                    x = tf.keras.layers.Conv2D(filters=2, kernel_size=kernel_size, activation=None, padding='SAME')(x)
                    return x

            with tf.name_scope('module_feat'):
                mfeat = module_feat()
                tensor_features1 = mfeat(tensor_features1)
                tensor_features2 = mfeat(tensor_features2)

            tensorFlow1 = tensorFlow * self.dblBackward[int_level]
            tensor_features2 = tf_warp(tensor_features2, tensorFlow1)
            tens_flow = tf.concat([tensor_features1, tensor_features2, tensorFlow], -1)

            return (tensorFlow if tensorFlow is not None else 0.0) + module_main(tens_flow)

    def regularization(self, tensor1, tensor2, tensor_features1, tensor_features2, tensorFlow, int_level, name='module_regularization'):
        with tf.name_scope(name):
            lrelu = lambda x: tf.nn.leaky_relu(x, 0.1)
            int_unfold = [1, 1, 7, 5, 5, 3, 3][int_level]

            def module_feat(x):
                with tf.name_scope('module_feat'):
                    if int_level < 5:
                        return tf.keras.layers.Conv2D(filters=128, kernel_size=1, activation=lrelu, padding='valid')(x)
                    else:
                        return x

            moduleScaleY = lambda x: tf.keras.layers.Conv2D(filters=1, kernel_size=1, activation=None, padding='valid')(
                x)
            moduleScaleX = lambda x: tf.keras.layers.Conv2D(filters=1, kernel_size=1, activation=None, padding='valid')(
                x)

            def module_main(x):
                with tf.name_scope('module_main'):
                    conv1 = tf.keras.layers.Conv2D(filters=128, kernel_size=3, activation=lrelu, padding='SAME')(x)
                    conv2 = tf.keras.layers.Conv2D(filters=128, kernel_size=3, activation=lrelu, padding='SAME')(conv1)
                    conv3 = tf.keras.layers.Conv2D(filters=64, kernel_size=3, activation=lrelu, padding='SAME')(conv2)
                    conv4 = tf.keras.layers.Conv2D(filters=64, kernel_size=3, activation=lrelu, padding='SAME')(conv3)
                    conv5 = tf.keras.layers.Conv2D(filters=32, kernel_size=3, activation=lrelu, padding='SAME')(conv4)
                    conv6 = tf.keras.layers.Conv2D(filters=32, kernel_size=3, activation=lrelu, padding='SAME')(conv5)
                    return conv6

            def module_dist(x):
                with tf.name_scope('module_dist'):
                    kernel_size = [1, 1, 7, 5, 5, 3, 3][int_level]
                    out_channels = [1, 1, 49, 25, 25, 9, 9][int_level]

                    if int_level >= 5:
                        return tf.keras.layers.Conv2D(filters=out_channels, kernel_size=kernel_size, padding='SAME', activation=None,)(x)
                    else:
                        x = tf.keras.layers.Conv2D(filters=out_channels, kernel_size=(kernel_size, 1), activation=None,
                                                   padding='same')(x)
                        x = tf.keras.layers.Conv2D(filters=out_channels, kernel_size=(1, kernel_size), activation=None,
                                                   padding='same')(x)

                        return x

            tensor_diff = tf.sqrt(
                tf.reduce_sum(tf.square(tensor1 - tf_warp(tensor2, tensorFlow * self.dblBackward[int_level])),
                              axis=3, keepdims=True))
            feat = module_feat(tensor_features1)
            tensor_dist = module_dist(module_main(tf.concat([tensor_diff,
                                                             tensorFlow - tf.reduce_mean(tensorFlow, keepdims=True,
                                                                                         axis=[1, 2]),
                                                             feat
                                                             ], 3)))
            tensor_dist = -tf.square(tensor_dist)
            tensor_dist = tf.exp(tensor_dist - tf.reduce_max(tensor_dist, axis=3, keepdims=True))

            tensor_div = 1. / tf.reduce_sum(tensor_dist, -1, keepdims=True)

            with tf.name_scope('moduleScaleX'):
                tensorScaleX = moduleScaleX(tensor_dist *
                                            tf.image.extract_patches(tensorFlow[..., 0:1],
                                                                     [1, int_unfold, int_unfold, 1],
                                                                     [1, 1, 1, 1],
                                                                     [1, 1, 1, 1],
                                                                     "SAME"))

            with tf.name_scope('moduleScaleY'):
                tensorScaleY = moduleScaleY(tensor_dist *
                                            tf.image.extract_patches(tensorFlow[..., 1:2],
                                                                     [1, int_unfold, int_unfold, 1],
                                                                     [1, 1, 1, 1],
                                                                     [1, 1, 1, 1],
                                                                     "SAME"))

            return tf.concat([tensorScaleX * tensor_div, tensorScaleY * tensor_div], -1)

    def correct_pan(self, x):
        with tf.name_scope('correct_pan'):
            lrelu = lambda x: tf.nn.leaky_relu(x, 0.1)
            conv1 = tf.keras.layers.Conv2D(filters=64, kernel_size=3, activation=lrelu, padding='SAME')(x)
            conv2 = tf.keras.layers.Conv2D(filters=32, kernel_size=3, activation=lrelu, padding='SAME')(conv1)
            conv3 = tf.keras.layers.Conv2D(filters=1, kernel_size=1, activation=None, padding='valid')(conv2)

        return tf.nn.tanh(conv3)

    def module_chromas(self, x):
        with tf.name_scope('module_chromas'):
            lrelu = lambda x: tf.nn.leaky_relu(x, 0.1)
            conv1 = tf.keras.layers.Conv2D(filters=32, kernel_size=3, activation=lrelu, padding='SAME')(x)
            conv2 = tf.keras.layers.Conv2D(filters=2, kernel_size=1, activation=None, padding='valid')(conv1)

        return conv2

    def __call__(self, tensor1, tensor2, scope='flownet'):
        tf.keras.backend.set_floatx('float32')
        with tf.name_scope(scope):
            tensor1_norm = tensor1 - [[[[0.411618, 0.434631, 0.454253]]]]
            tensor2_norm = tensor2 - [[[[0.410782, 0.433645, 0.452793]]]]

            m1, m2, m3, m4, m5, m6 = self.feature_extractor()

            def shared_feat_modules(x):
                with tf.name_scope('feature_extractor'):
                    t1 = m1(x)
                    t2 = m2(t1)
                    t3 = m3(t2)
                    t4 = m4(t3)
                    t5 = m5(t4)
                    t6 = m6(t5)
                return [t1, t2, t3, t4, t5, t6]

            tensor_feat1 = shared_feat_modules(tensor1_norm)
            tensor_feat2 = shared_feat_modules(tensor2_norm)

            self.tensor_features = tensor_feat1

            tensor1 = [tensor1_norm]
            tensor2 = [tensor2_norm]
            for i in [1, 2, 3, 4, 5]:
                tensor1.append(tf.image.resize(tensor1[-1], tf.shape(tensor_feat1[i])[1:3]))
                tensor2.append(tf.image.resize(tensor2[-1], tf.shape(tensor_feat2[i])[1:3]))

            flow = None
            lvls = [2, 3, 4, 5, 6]
            for i in [-1, -2, -3, -4, -5]:
                flow = self.matching(tensor_feat1[i], tensor_feat2[i], flow, lvls[i], name='matching_%i' % abs(i))
                flow = self.subpixel(tensor_feat1[i], tensor_feat2[i], flow, lvls[i], name='subpixel_%i' % abs(i))
                flow = self.regularization(tensor1[i], tensor2[i], tensor_feat1[i], tensor_feat2[i], flow, lvls[i], name='regularization_%i' % abs(i))

            flowr = tf.image.resize(flow, tf.shape(tensor1_norm)[1:3])

            return flowr * 20.0
