from __future__ import division
import os
import time
import math
from glob import glob
import tensorflow as tf
import numpy as np
import re
from six.moves import xrange, cPickle

from ops import *
from utils import *

def conv_out_size_same(size, stride):
    return int(math.ceil(float(size) / float(stride)))

class DCGAN(object):
    def __init__(self, sess, model_name = 'DCGAN', input_height=64, input_width=64, output_height=64, output_width=64,
        batch_size=64, sample_num = 64, y_dim=4800, z_dim=100, gf_dim=64, df_dim=64, t_dim=256,
        dataset_name='faces', input_fname_pattern='*.jpg', crop=False,
        gfc_dim=1024, dfc_dim=1024, c_dim=3,  
        save_dir='save_DCGAN', temp_samples_dir='temp_samples_DCGAN',
        tag_filename='vec_hair_eyes.pkl', tag_filename_sp='blonde_hair_blue_eyes.pkl', infer=False):
        """
        Args:
          sess: TensorFlow session
          batch_size: The size of batch. Should be specified before training.
          y_dim: (optional) Dimension of dim for y. [None]
          z_dim: (optional) Dimension of dim for Z. [100]
          gf_dim: (optional) Dimension of gen filters in first conv layer. [64]
          df_dim: (optional) Dimension of discrim filters in first conv layer. [64]
          gfc_dim: (optional) Dimension of gen units for for fully connected layer. [1024]
          dfc_dim: (optional) Dimension of discrim units for fully connected layer. [1024]
          c_dim: (optional) Dimension of image color. For grayscale input, set to 1. [3]
        """
        self.sess = sess
        self.model_name = model_name
        self.crop = crop
        self.batch_size = batch_size
        self.sample_num = sample_num
        self.input_height = input_height
        self.input_width = input_width
        self.output_height = output_height
        self.output_width = output_width
        self.y_dim = y_dim
        self.z_dim = z_dim
        self.gf_dim = gf_dim
        self.df_dim = df_dim
        self.gfc_dim = gfc_dim
        self.dfc_dim = dfc_dim

        # batch normalization : deals with poor initialization helps gradient flow
        self.d_bn1 = batch_norm(name='d_bn1')
        self.d_bn2 = batch_norm(name='d_bn2')
        self.d_bn3 = batch_norm(name='d_bn3')
        self.d_bn4 = batch_norm(name='d_bn4')
        self.g_bn0 = batch_norm(name='g_bn0')
        self.g_bn1 = batch_norm(name='g_bn1')
        self.g_bn2 = batch_norm(name='g_bn2')
        self.g_bn3 = batch_norm(name='g_bn3')

        self.dataset_name = dataset_name
        self.input_fname_pattern = input_fname_pattern
        self.save_dir = save_dir
        self.temp_samples_dir = temp_samples_dir

        ## tags are dictionary {2: embedding of 'blonde hair pink eyes', 3: embedding of 'blonde hair long hair purple eyes', ...}
        if not infer:
            try:
                self.tags = cPickle.load(open(tag_filename, 'rb'))
                self.tags_sp = cPickle.load(open(tag_filename_sp, 'rb'))
            except:
                self.tags = cPickle.load(open(tag_filename, 'rb'), encoding='latin1')
                self.tags_sp = cPickle.load(open(tag_filename_sp, 'rb'), encoding='latin1')
            self.file_names = list(self.tags.keys())
            data_all = glob(os.path.join(self.dataset_name, self.input_fname_pattern))
            self.data = [file_path for file_path in data_all if int(re.split('\\.', os.path.basename(file_path))[0]) in self.file_names]

        self.c_dim = c_dim
        self.t_dim = t_dim

        ## Build model in train.py explicitly!
        # self.build_model()

    def build_model(self):
        self.y = tf.placeholder(tf.float32, [self.batch_size, self.y_dim], name='y')
        self.y_random = tf.placeholder(tf.float32, [self.batch_size, self.y_dim], name='y_random')

        if self.crop:
            image_dims = [self.output_height, self.output_width, self.c_dim]
        else:
            image_dims = [self.input_height, self.input_width, self.c_dim]

        self.inputs = tf.placeholder(tf.float32, [self.batch_size] + image_dims, name='real_images')
        self.sample_inputs = tf.placeholder(tf.float32, [self.sample_num] + image_dims, name='sample_inputs')
        inputs = self.inputs
        sample_inputs = self.sample_inputs
        self.z = tf.placeholder(tf.float32, [None, self.z_dim], name='z')
        self.z_sum = histogram_summary("z", self.z)
        self.G = self.generator(self.z, self.y)
        self.sampler = self.sampler(self.z, self.y)
        self.D_real, self.D_logits_real = self.discriminator(inputs, self.y, reuse=False)
        self.D_fake, self.D_logits_fake = self.discriminator(self.G, self.y, reuse=True)
        self.D_wrong, self.D_logits_wrong = self.discriminator(inputs, self.y_random, reuse=True)
        self.d_real_sum = histogram_summary("d_real", self.D_real)
        self.d_fake_sum = histogram_summary("d_fake", self.D_fake)
        self.d_wrong_sum = histogram_summary("d_wrong", self.D_wrong)
        self.G_sum = image_summary("G", self.G)

        def sigmoid_cross_entropy_with_logits(x, y):
            try:
                return tf.nn.sigmoid_cross_entropy_with_logits(logits=x, labels=y)
            except:
                return tf.nn.sigmoid_cross_entropy_with_logits(logits=x, targets=y)

        self.d_loss_real = tf.reduce_mean(
            sigmoid_cross_entropy_with_logits(self.D_logits_real, tf.ones_like(self.D_real)))
        self.d_loss_fake = tf.reduce_mean(
            sigmoid_cross_entropy_with_logits(self.D_logits_fake, tf.zeros_like(self.D_fake)))
        self.d_loss_wrong = tf.reduce_mean(
            sigmoid_cross_entropy_with_logits(self.D_logits_wrong, tf.zeros_like(self.D_wrong)))
        self.g_loss = tf.reduce_mean(
            sigmoid_cross_entropy_with_logits(self.D_logits_fake, tf.ones_like(self.D_fake)))
        self.d_loss_real_sum = scalar_summary("d_loss_real", self.d_loss_real)
        self.d_loss_fake_sum = scalar_summary("d_loss_fake", self.d_loss_fake)
        self.d_loss_wrong_sum = scalar_summary("d_loss_wrong", self.d_loss_wrong)
        self.d_loss = self.d_loss_real + self.d_loss_fake + self.d_loss_wrong
        self.g_loss_sum = scalar_summary("g_loss", self.g_loss)
        self.d_loss_sum = scalar_summary("d_loss", self.d_loss)
        t_vars = tf.trainable_variables()
        self.d_vars = [var for var in t_vars if 'd_' in var.name]
        self.g_vars = [var for var in t_vars if 'g_' in var.name]
        self.saver = tf.train.Saver(max_to_keep = None) ## keep all checkpoints!

    ## Pass config to obtain learning_rate, beta1, train_size, and epoch
    def train(self, config):
        d_optim = tf.train.AdamOptimizer(config.learning_rate, beta1=config.beta1).minimize(self.d_loss, var_list=self.d_vars)
        g_optim = tf.train.AdamOptimizer(config.learning_rate, beta1=config.beta1).minimize(self.g_loss, var_list=self.g_vars)

        try:
            tf.global_variables_initializer().run()
        except:
            tf.initialize_all_variables().run()

        self.g_sum = merge_summary([self.z_sum, self.d_fake_sum, self.G_sum, self.d_loss_fake_sum, self.g_loss_sum])
        self.d_sum = merge_summary([self.z_sum, self.d_real_sum, self.d_loss_real_sum, self.d_loss_sum])
        self.writer = SummaryWriter('./logs_' + self.model_name, self.sess.graph)
        sample_z = np.random.uniform(-1, 1, size=(self.sample_num , self.z_dim))
        sample_files = self.data[0:self.sample_num]
        sample = [
            get_image(sample_file,
                input_height=self.input_height,
                input_width=self.input_width,
                resize_height=self.output_height,
                resize_width=self.output_width,
                crop=self.crop) for sample_file in sample_files]
        sample_inputs = np.array(sample).astype(np.float32)
        
        counter = 1
        start_time = time.time()
        if config.init_from is not None:
            could_load, checkpoint_counter = self.load(config.init_from)
            if could_load:
                counter = checkpoint_counter
                print(" [*] Load SUCCESS")
            else:
                print(" [!] Load failed...")
        else:
            print(" [@] train from scratch")

        errD_list = list()
        errG_list = list()
        for epoch in xrange(config.epoch):
            batch_idxs = min(len(self.data), config.train_size) // self.batch_size
            for idx in xrange(0, batch_idxs):
                # print('epoch = %d, idx = %d'%(epoch, idx))
                batch_files = self.data[idx*self.batch_size:(idx+1)*self.batch_size]
                batch = [
                    get_image(batch_file,
                        input_height=self.input_height,
                        input_width=self.input_width,
                        resize_height=self.output_height,
                        resize_width=self.output_width,
                        crop=self.crop) for batch_file in batch_files]
                batch_images = np.array(batch).astype(np.float32)

                batch_y = [self.tags[int(re.split("\\.", os.path.basename(batch_file))[0])] for batch_file in batch_files]
                batch_y = np.array(batch_y).astype(np.float32)

                # Update D network
                batch_z = np.random.uniform(-1, 1, [self.batch_size, self.z_dim]).astype(np.float32)
                ## random select texts as "wrong" texts
                batch_y_random = [self.tags[random_idx] for random_idx in np.random.choice(self.file_names, self.batch_size)]
                _, summary_str = self.sess.run([d_optim, self.d_sum],
                    feed_dict={ self.inputs: batch_images, self.z: batch_z, \
                                self.y: batch_y, self.y_random: batch_y_random })
                self.writer.add_summary(summary_str, counter)

                # Update G network
                batch_z = np.random.uniform(-1, 1, [self.batch_size, self.z_dim]).astype(np.float32)
                ## random select texts as "wrong" texts
                batch_y_random = [self.tags[random_idx] for random_idx in np.random.choice(self.file_names, self.batch_size)]
                _, summary_str = self.sess.run([g_optim, self.g_sum],
                    feed_dict={ self.z: batch_z, self.y: batch_y })
                self.writer.add_summary(summary_str, counter)

                # Run g_optim twice to make sure that d_loss does not go to zero (different from paper)
                batch_z = np.random.uniform(-1, 1, [self.batch_size, self.z_dim]).astype(np.float32)
                ## random select texts as "wrong" texts
                batch_y_random = [self.tags[random_idx] for random_idx in np.random.choice(self.file_names, self.batch_size)]
                _, summary_str = self.sess.run([g_optim, self.g_sum],
                    feed_dict={ self.z: batch_z, self.y: batch_y })
                self.writer.add_summary(summary_str, counter)
                
                errD_fake = self.d_loss_fake.eval({ self.z: batch_z, self.y: batch_y })
                errD_real = self.d_loss_real.eval({ self.inputs: batch_images, self.y: batch_y })
                errD_wrong = self.d_loss_wrong.eval({ self.inputs: batch_images, self.y_random: batch_y_random })
                errG = self.g_loss.eval({self.z: batch_z, self.y: batch_y})

                counter += 1
                print("Epoch: [%2d] [%4d/%4d] time: %4.4f, d_loss: %.8f, g_loss: %.8f" \
                    % (epoch, idx, batch_idxs, time.time() - start_time, errD_real+errD_fake+errD_wrong, errG))
                errD_list.append(errD_real+errD_fake+errD_wrong)
                errG_list.append(errG)

                if np.mod(counter, 500) == 1:
                    try:
                        samples, d_loss, g_loss = self.sess.run(
                            [self.sampler, self.d_loss, self.g_loss],
                                feed_dict={ self.z: sample_z,
                                            self.inputs: sample_inputs,
                                            self.y: batch_y,
                                            self.y_random: batch_y_random})
                        manifold_h = int(np.ceil(np.sqrt(samples.shape[0])))
                        manifold_w = int(np.floor(np.sqrt(samples.shape[0])))
                        save_images(samples, [manifold_h, manifold_w],
                                    './{}/train_{:02d}_{:04d}.png'.format(self.temp_samples_dir, epoch, idx))
                        print("[Sample] d_loss: %.8f, g_loss: %.8f" % (d_loss, g_loss)) 
                    except:
                        print("one pic error!...")
                
                if np.mod(counter, 2000) == 2:
                    self.save(self.save_dir, counter)
                    ## Overwrite
                    cPickle.dump(errD_list, open(os.path.join(self.save_dir, 'errD_list.pkl'), 'wb'))
                    cPickle.dump(errG_list, open(os.path.join(self.save_dir, 'errG_list.pkl'), 'wb'))

    def discriminator(self, image, y=None, reuse=False):
        with tf.variable_scope("discriminator") as scope:
            if reuse:
                scope.reuse_variables()
            h0 = lrelu(conv2d(image, self.df_dim, name='d_h0_conv'))            ## h0: [-1, 32, 32, df_dim]
            h1 = lrelu(self.d_bn1(conv2d(h0, self.df_dim*2, name='d_h1_conv')))  ## h1: [-1, 16, 16, df_dim*2]
            h2 = lrelu(self.d_bn2(conv2d(h1, self.df_dim*4, name='d_h2_conv')))  ## h2: [-1, 8, 8, df_dim*4]
            h3 = lrelu(self.d_bn3(conv2d(h2, self.df_dim*8, name='d_h3_conv')))  ## h3: [-1, 4, 4, df_dim*8]
            yb = lrelu(linear(y, self.t_dim, 'd_embedding'))
            yb = tf.expand_dims(yb,1)
            yb = tf.expand_dims(yb,2)
            yb = tf.tile(yb, [1,4,4,1], name='tiled_embeddings')
            h3_concat = concat([h3, yb], 3, name='h3_concat')
            h3_new = lrelu(self.d_bn4(conv2d(h3_concat, self.df_dim*8, 1,1,1,1, \
                name = 'd_h3_conv_new'))) ## h3_new: [-1, 4, 4, df_dim*8]
            h4 = linear(tf.reshape(h3_new, [self.batch_size, -1]), 1, 'd_h3_lin')
            return tf.nn.sigmoid(h4), h4

    def generator(self, z, y=None):
        with tf.variable_scope("generator") as scope:
            s_h, s_w = self.output_height, self.output_width                        ## 64, 64
            s_h2, s_w2 = conv_out_size_same(s_h, 2), conv_out_size_same(s_w, 2)     ## 32, 32
            s_h4, s_w4 = conv_out_size_same(s_h2, 2), conv_out_size_same(s_w2, 2)   ## 16, 16
            s_h8, s_w8 = conv_out_size_same(s_h4, 2), conv_out_size_same(s_w4, 2)   ## 8, 8
            s_h16, s_w16 = conv_out_size_same(s_h8, 2), conv_out_size_same(s_w8, 2) ## 4, 4
            yb = lrelu(linear(y, self.t_dim, 'g_embedding'))
            z = concat([z, yb], 1)
            z_ = linear(z, self.gf_dim*8*s_h16*s_w16, 'g_h0_lin')
            h0 = tf.reshape(z_, [-1, s_h16, s_w16, self.gf_dim*8])
            h0 = tf.nn.relu(self.g_bn0(h0))
            h1 = deconv2d(h0, [self.batch_size, s_h8, s_w8, self.gf_dim*4], name='g_h1')
            h1 = tf.nn.relu(self.g_bn1(h1))
            h2 = deconv2d(h1, [self.batch_size, s_h4, s_w4, self.gf_dim*2], name='g_h2')
            h2 = tf.nn.relu(self.g_bn2(h2))
            h3 = deconv2d(h2, [self.batch_size, s_h2, s_w2, self.gf_dim*1], name='g_h3')
            h3 = tf.nn.relu(self.g_bn3(h3))
            h4 = deconv2d(h3, [self.batch_size, s_h, s_w, self.c_dim], name='g_h4')
            return (tf.tanh(h4)/2. + 0.5)

    def sampler(self, z, y=None):
        with tf.variable_scope("generator") as scope:
            scope.reuse_variables()
            s_h, s_w = self.output_height, self.output_width                        ## 64, 64
            s_h2, s_w2 = conv_out_size_same(s_h, 2), conv_out_size_same(s_w, 2)     ## 32, 32
            s_h4, s_w4 = conv_out_size_same(s_h2, 2), conv_out_size_same(s_w2, 2)   ## 16, 16
            s_h8, s_w8 = conv_out_size_same(s_h4, 2), conv_out_size_same(s_w4, 2)   ## 8, 8
            s_h16, s_w16 = conv_out_size_same(s_h8, 2), conv_out_size_same(s_w8, 2) ## 4, 4
            yb = lrelu(linear(y, self.t_dim, 'g_embedding'))
            z = concat([z, yb], 1)
            z_ = linear(z, self.gf_dim*8*s_h16*s_w16, 'g_h0_lin')
            h0 = tf.reshape(z_, [-1, s_h16, s_w16, self.gf_dim*8])
            h0 = tf.nn.relu(self.g_bn0(h0, train=False))
            h1 = deconv2d(h0, [self.batch_size, s_h8, s_w8, self.gf_dim*4], name='g_h1')
            h1 = tf.nn.relu(self.g_bn1(h1, train=False))
            h2 = deconv2d(h1, [self.batch_size, s_h4, s_w4, self.gf_dim*2], name='g_h2')
            h2 = tf.nn.relu(self.g_bn2(h2, train=False))
            h3 = deconv2d(h2, [self.batch_size, s_h2, s_w2, self.gf_dim*1], name='g_h3')
            h3 = tf.nn.relu(self.g_bn3(h3, train=False))
            h4 = deconv2d(h3, [self.batch_size, s_h, s_w, self.c_dim], name='g_h4')
            return (tf.tanh(h4)/2. + 0.5)

    @property
    def model_dir(self):
        return "{}_{}_{}_{}".format(
            self.dataset_name, self.batch_size,
            self.output_height, self.output_width)

    def save(self, save_dir, step):
        model_name = self.model_name + ".model"
        save_dir = os.path.join(save_dir, self.model_dir)
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        self.saver.save(self.sess,
            os.path.join(save_dir, model_name), global_step=step)

    def load(self, save_dir):
        import re
        print(" [*] Reading checkpoints...")
        save_dir = os.path.join(save_dir, self.model_dir)
        ckpt = tf.train.get_checkpoint_state(save_dir)
        if ckpt and ckpt.model_checkpoint_path:
            ckpt_name = os.path.basename(ckpt.model_checkpoint_path)
            self.saver.restore(self.sess, os.path.join(save_dir, ckpt_name))
            counter = int(next(re.finditer("(\d+)(?!.*\d)",ckpt_name)).group(0))
            print(" [*] Success to read {}".format(ckpt_name))
            return True, counter
        else:
            print(" [*] Failed to find a checkpoint")
            return False, 0

class WGAN(DCGAN):
    ## Reuse init function of DCGAN
    def __init__(self, sess, model_name = 'WGAN', input_height=64, input_width=64, output_height=64, output_width=64,
        batch_size=64, sample_num = 64, y_dim=4800, z_dim=100, gf_dim=64, df_dim=64, t_dim=256,
        dataset_name='faces', input_fname_pattern='*.jpg', crop=False,
        gfc_dim=1024, dfc_dim=1024, c_dim=3,  
        save_dir='save_WGAN', temp_samples_dir='temp_samples_WGAN',
        tag_filename='vec_hair_eyes.pkl', tag_filename_sp='blonde_hair_blue_eyes.pkl', clipping_value=0.01, infer=False):
        super(WGAN, self).__init__(sess, model_name, input_height, input_width, output_height, output_width,
            batch_size, sample_num, y_dim, z_dim, gf_dim, df_dim, t_dim,
            dataset_name, input_fname_pattern, crop,
            gfc_dim, dfc_dim, c_dim,
            save_dir, temp_samples_dir,
            tag_filename, tag_filename_sp,infer)
        self.clipping_value = clipping_value
    ## Re-write build_model, train, and discriminator functions
    def build_model(self):
        self.y = tf.placeholder(tf.float32, [self.batch_size, self.y_dim], name='y')
        self.y_random = tf.placeholder(tf.float32, [self.batch_size, self.y_dim], name='y_random')

        if self.crop:
            image_dims = [self.output_height, self.output_width, self.c_dim]
        else:
            image_dims = [self.input_height, self.input_width, self.c_dim]

        self.inputs = tf.placeholder(tf.float32, [self.batch_size] + image_dims, name='real_images')
        self.sample_inputs = tf.placeholder(tf.float32, [self.sample_num] + image_dims, name='sample_inputs')
        inputs = self.inputs
        sample_inputs = self.sample_inputs
        self.z = tf.placeholder(tf.float32, [None, self.z_dim], name='z')
        self.z_sum = histogram_summary("z", self.z)
        self.G = self.generator(self.z, self.y)
        self.sampler = self.sampler(self.z, self.y)
        self.D_real = self.discriminator(inputs, self.y, reuse=False)
        self.D_fake = self.discriminator(self.G, self.y, reuse=True)
        self.D_wrong = self.discriminator(inputs, self.y_random, reuse=True)
        self.d_real_sum = histogram_summary("d_real", self.D_real)
        self.d_fake_sum = histogram_summary("d_fake", self.D_fake)
        self.d_wrong_sum = histogram_summary("d_wrong", self.D_wrong)
        self.G_sum = image_summary("G", self.G)

        def sigmoid_cross_entropy_with_logits(x, y):
            try:
                return tf.nn.sigmoid_cross_entropy_with_logits(logits=x, labels=y)
            except:
                return tf.nn.sigmoid_cross_entropy_with_logits(logits=x, targets=y)

        self.d_loss_real = tf.reduce_mean(self.D_real)
        self.d_loss_fake = tf.reduce_mean(self.D_fake)
        self.d_loss_wrong = tf.reduce_mean(self.D_wrong)
        self.g_loss = -tf.reduce_mean(self.D_fake)
        self.d_loss_real_sum = scalar_summary("d_loss_real", self.d_loss_real)
        self.d_loss_fake_sum = scalar_summary("d_loss_fake", self.d_loss_fake)
        self.d_loss_wrong_sum = scalar_summary("d_loss_wrong", self.d_loss_wrong)
        self.d_loss = self.d_loss_real - self.d_loss_fake - self.d_loss_wrong
        self.g_loss_sum = scalar_summary("g_loss", self.g_loss)
        self.d_loss_sum = scalar_summary("d_loss", self.d_loss)
        t_vars = tf.trainable_variables()
        self.d_vars = [var for var in t_vars if 'd_' in var.name]
        self.g_vars = [var for var in t_vars if 'g_' in var.name]
        self.saver = tf.train.Saver(max_to_keep = None) ## keep all checkpoints!

    def train(self, config):
        d_optim = tf.train.RMSPropOptimizer(config.learning_rate).minimize(-self.d_loss, var_list=self.d_vars)
        g_optim = tf.train.RMSPropOptimizer(config.learning_rate).minimize(self.g_loss, var_list=self.g_vars)
        clip_D = [p.assign(tf.clip_by_value(p, -self.clipping_value, self.clipping_value)) for p in self.d_vars]

        try:
            tf.global_variables_initializer().run()
        except:
            tf.initialize_all_variables().run()

        self.g_sum = merge_summary([self.z_sum, self.d_fake_sum, self.G_sum, self.d_loss_fake_sum, self.g_loss_sum])
        self.d_sum = merge_summary([self.z_sum, self.d_real_sum, self.d_loss_real_sum, self.d_loss_sum])
        self.writer = SummaryWriter('./logs_' + self.model_name, self.sess.graph)
        sample_z = np.random.uniform(-1, 1, size=(self.sample_num , self.z_dim))
        sample_files = self.data[0:self.sample_num]
        sample = [
            get_image(sample_file,
                input_height=self.input_height,
                input_width=self.input_width,
                resize_height=self.output_height,
                resize_width=self.output_width,
                crop=self.crop) for sample_file in sample_files]
        sample_inputs = np.array(sample).astype(np.float32)
        
        counter = 1
        start_time = time.time()
        if config.init_from is not None:
            could_load, checkpoint_counter = self.load(config.init_from)
            if could_load:
                counter = checkpoint_counter
                print(" [*] Load SUCCESS")
            else:
                print(" [!] Load failed...")
        else:
            print(" [@] train from scratch")

        errD_list = list()
        errG_list = list()
        for epoch in xrange(config.epoch):
            batch_idxs = min(len(self.data), config.train_size) // self.batch_size
            for idx in xrange(0, batch_idxs):
                # print('epoch = %d, idx = %d'%(epoch, idx))
                batch_files = self.data[idx*self.batch_size:(idx+1)*self.batch_size]
                batch = [
                    get_image(batch_file,
                        input_height=self.input_height,
                        input_width=self.input_width,
                        resize_height=self.output_height,
                        resize_width=self.output_width,
                        crop=self.crop) for batch_file in batch_files]
                batch_images = np.array(batch).astype(np.float32)

                batch_y = [self.tags[int(re.split("\\.", os.path.basename(batch_file))[0])] for batch_file in batch_files]
                batch_y = np.array(batch_y).astype(np.float32)

                ## Update D network five times
                for _ in range(5):
                    batch_z = np.random.uniform(-1, 1, [self.batch_size, self.z_dim]).astype(np.float32)
                    ## random select texts as "wrong" texts
                    batch_y_random = [self.tags[random_idx] for random_idx in np.random.choice(self.file_names, self.batch_size)]
                    _, summary_str, _ = self.sess.run([d_optim, self.d_sum, clip_D],
                        feed_dict={ self.inputs: batch_images, self.z: batch_z, \
                                    self.y: batch_y, self.y_random: batch_y_random })
                    self.writer.add_summary(summary_str, counter)

                # Update G network once
                batch_z = np.random.uniform(-1, 1, [self.batch_size, self.z_dim]).astype(np.float32)
                _, summary_str = self.sess.run([g_optim, self.g_sum],
                    feed_dict={ self.z: batch_z, self.y: batch_y })
                self.writer.add_summary(summary_str, counter)
                
                errD_fake = self.d_loss_fake.eval({ self.z: batch_z, self.y: batch_y })
                errD_real = self.d_loss_real.eval({ self.inputs: batch_images, self.y: batch_y })
                errD_wrong = self.d_loss_wrong.eval({ self.inputs: batch_images, self.y_random: batch_y_random })
                errG = self.g_loss.eval({self.z: batch_z, self.y: batch_y})

                counter += 1
                print("Epoch: [%2d] [%4d/%4d] time: %4.4f, d_loss: %.8f, g_loss: %.8f" \
                    % (epoch, idx, batch_idxs, time.time() - start_time, errD_real-errD_fake-errD_wrong, errG))
                errD_list.append(errD_real-errD_fake-errD_wrong)
                errG_list.append(errG)

                if np.mod(counter, 500) == 1:
                    try:
                        samples, d_loss, g_loss = self.sess.run(
                            [self.sampler, self.d_loss, self.g_loss],
                                feed_dict={ self.z: sample_z,
                                            self.inputs: sample_inputs,
                                            self.y: batch_y,
                                            self.y_random: batch_y_random})
                        manifold_h = int(np.ceil(np.sqrt(samples.shape[0])))
                        manifold_w = int(np.floor(np.sqrt(samples.shape[0])))
                        save_images(samples, [manifold_h, manifold_w],
                                    './{}/train_{:02d}_{:04d}.png'.format(self.temp_samples_dir, epoch, idx))
                        print("[Sample] d_loss: %.8f, g_loss: %.8f" % (d_loss, g_loss)) 
                    except:
                        print("one pic error!...")
                
                if np.mod(counter, 2000) == 2:
                    self.save(self.save_dir, counter)
                    ## Overwrite
                    cPickle.dump(errD_list, open(os.path.join(self.save_dir, 'errD_list.pkl'), 'wb'))
                    cPickle.dump(errG_list, open(os.path.join(self.save_dir, 'errG_list.pkl'), 'wb'))

    def discriminator(self, image, y=None, reuse=False):
        with tf.variable_scope("discriminator") as scope:
            if reuse:
                scope.reuse_variables()
            h0 = lrelu(conv2d(image, self.df_dim, name='d_h0_conv'))            ## h0: [-1, 32, 32, df_dim]
            h1 = lrelu(self.d_bn1(conv2d(h0, self.df_dim*2, name='d_h1_conv')))  ## h1: [-1, 16, 16, df_dim*2]
            h2 = lrelu(self.d_bn2(conv2d(h1, self.df_dim*4, name='d_h2_conv')))  ## h2: [-1, 8, 8, df_dim*4]
            h3 = lrelu(self.d_bn3(conv2d(h2, self.df_dim*8, name='d_h3_conv')))  ## h3: [-1, 4, 4, df_dim*8]
            yb = lrelu(linear(y, self.t_dim, 'd_embedding'))
            yb = tf.expand_dims(yb,1)
            yb = tf.expand_dims(yb,2)
            yb = tf.tile(yb, [1,4,4,1], name='tiled_embeddings')
            h3_concat = concat([h3, yb], 3, name='h3_concat')
            h3_new = lrelu(self.d_bn4(conv2d(h3_concat, self.df_dim*8, 1,1,1,1, \
                name = 'd_h3_conv_new'))) ## h3_new: [-1, 4, 4, df_dim*8]
            h4 = linear(tf.reshape(h3_new, [self.batch_size, -1]), 1, 'd_h3_lin')
            return h4

class WGAN_v2(DCGAN):
    ## Reuse init function of DCGAN
    def __init__(self, sess, model_name = 'WGAN_v2', input_height=64, input_width=64, output_height=64, output_width=64,
        batch_size=64, sample_num = 64, y_dim=4800, z_dim=100, gf_dim=64, df_dim=64, t_dim=256,
        dataset_name='faces', input_fname_pattern='*.jpg', crop=False,
        gfc_dim=1024, dfc_dim=1024, c_dim=3,  
        save_dir='save_WGAN_v2', temp_samples_dir='temp_samples_WGAN_v2',
        tag_filename='vec_hair_eyes.pkl', tag_filename_sp='blonde_hair_blue_eyes.pkl', scale=10.0,infer=False):
        super(WGAN_v2, self).__init__(sess, model_name, input_height, input_width, output_height, output_width,
            batch_size, sample_num, y_dim, z_dim, gf_dim, df_dim, t_dim,
            dataset_name, input_fname_pattern, crop,
            gfc_dim, dfc_dim, c_dim,
            save_dir, temp_samples_dir,
            tag_filename, tag_filename_sp,infer)
        self.scale = scale
    ## Re-write build_model, train, and discriminator functions
    def build_model(self):
        self.y = tf.placeholder(tf.float32, [self.batch_size, self.y_dim], name='y')
        self.y_random = tf.placeholder(tf.float32, [self.batch_size, self.y_dim], name='y_random')

        if self.crop:
            image_dims = [self.output_height, self.output_width, self.c_dim]
        else:
            image_dims = [self.input_height, self.input_width, self.c_dim]

        self.inputs = tf.placeholder(tf.float32, [self.batch_size] + image_dims, name='real_images')
        self.sample_inputs = tf.placeholder(tf.float32, [self.sample_num] + image_dims, name='sample_inputs')
        inputs = self.inputs
        sample_inputs = self.sample_inputs
        self.z = tf.placeholder(tf.float32, [None, self.z_dim], name='z')
        self.z_sum = histogram_summary("z", self.z)
        self.G = self.generator(self.z, self.y)
        self.sampler = self.sampler(self.z, self.y)
        self.D_real = self.discriminator(inputs, self.y, reuse=False)
        self.D_fake = self.discriminator(self.G, self.y, reuse=True)
        self.D_wrong = self.discriminator(inputs, self.y_random, reuse=True)
        self.d_real_sum = histogram_summary("d_real", self.D_real)
        self.d_fake_sum = histogram_summary("d_fake", self.D_fake)
        self.d_wrong_sum = histogram_summary("d_wrong", self.D_wrong)
        self.G_sum = image_summary("G", self.G)

        def sigmoid_cross_entropy_with_logits(x, y):
            try:
                return tf.nn.sigmoid_cross_entropy_with_logits(logits=x, labels=y)
            except:
                return tf.nn.sigmoid_cross_entropy_with_logits(logits=x, targets=y)

        self.d_loss_real = tf.reduce_mean(self.D_real)
        self.d_loss_fake = tf.reduce_mean(self.D_fake)
        self.d_loss_wrong = tf.reduce_mean(self.D_wrong)
        self.g_loss = -tf.reduce_mean(self.D_fake)
        self.d_loss_real_sum = scalar_summary("d_loss_real", self.d_loss_real)
        self.d_loss_fake_sum = scalar_summary("d_loss_fake", self.d_loss_fake)
        self.d_loss_wrong_sum = scalar_summary("d_loss_wrong", self.d_loss_wrong)
        self.d_loss = self.d_loss_real - self.d_loss_fake - self.d_loss_wrong

        ## improved W-GAN (gradient penalty)
        epsilon = tf.random_uniform([], 0.0, 1.0)
        x_hat = epsilon * inputs + (1 - epsilon) * self.G
        d_hat = self.discriminator(x_hat, self.y, reuse=True)
        self.ddx = tf.gradients(d_hat, x_hat)[0]
        self.ddx = tf.sqrt(tf.reduce_sum(tf.square(self.ddx), axis=1))
        self.ddx = tf.reduce_mean(tf.square(self.ddx - 1.0) * self.scale)
        self.d_loss = self.d_loss - self.ddx

        self.g_loss_sum = scalar_summary("g_loss", self.g_loss)
        self.d_loss_sum = scalar_summary("d_loss", self.d_loss)
        t_vars = tf.trainable_variables()
        self.d_vars = [var for var in t_vars if 'd_' in var.name]
        self.g_vars = [var for var in t_vars if 'g_' in var.name]
        self.saver = tf.train.Saver(max_to_keep = None) ## keep all checkpoints!

    def train(self, config):
        d_optim = tf.train.AdamOptimizer(config.learning_rate, beta1=config.beta1).minimize(-self.d_loss, var_list=self.d_vars)
        g_optim = tf.train.AdamOptimizer(config.learning_rate, beta1=config.beta1).minimize(self.g_loss, var_list=self.g_vars)

        try:
            tf.global_variables_initializer().run()
        except:
            tf.initialize_all_variables().run()

        self.g_sum = merge_summary([self.z_sum, self.d_fake_sum, self.G_sum, self.d_loss_fake_sum, self.g_loss_sum])
        self.d_sum = merge_summary([self.z_sum, self.d_real_sum, self.d_loss_real_sum, self.d_loss_sum])
        self.writer = SummaryWriter('./logs_' + self.model_name, self.sess.graph)
        sample_z = np.random.uniform(-1, 1, size=(self.sample_num , self.z_dim))
        sample_files = self.data[0:self.sample_num]
        sample = [
            get_image(sample_file,
                input_height=self.input_height,
                input_width=self.input_width,
                resize_height=self.output_height,
                resize_width=self.output_width,
                crop=self.crop) for sample_file in sample_files]
        sample_inputs = np.array(sample).astype(np.float32)
        
        counter = 1
        start_time = time.time()
        if config.init_from is not None:
            could_load, checkpoint_counter = self.load(config.init_from)
            if could_load:
                counter = checkpoint_counter
                print(" [*] Load SUCCESS")
            else:
                print(" [!] Load failed...")
        else:
            print(" [@] train from scratch")

        errD_list = list()
        errG_list = list()
        for epoch in xrange(config.epoch):
            batch_idxs = min(len(self.data), config.train_size) // self.batch_size
            for idx in xrange(0, batch_idxs):
                # print('epoch = %d, idx = %d'%(epoch, idx))
                batch_files = self.data[idx*self.batch_size:(idx+1)*self.batch_size]
                batch = [
                    get_image(batch_file,
                        input_height=self.input_height,
                        input_width=self.input_width,
                        resize_height=self.output_height,
                        resize_width=self.output_width,
                        crop=self.crop) for batch_file in batch_files]
                batch_images = np.array(batch).astype(np.float32)

                batch_y = [self.tags[int(re.split("\\.", os.path.basename(batch_file))[0])] for batch_file in batch_files]
                batch_y = np.array(batch_y).astype(np.float32)

                ## 2017/05/23:
                ## (Special test) if y_dim == 9600
                ## ==> Use self.tags to read hair vectors and self.tags_sp to read eyes vectors
                if self.y_dim == 9600:
                    batch_y_2 = [self.tags_sp[int(re.split("\\.", os.path.basename(batch_file))[0])] for batch_file in batch_files]
                    batch_y_2 = np.array(batch_y_2).astype(np.float32)
                    batch_y = np.concatenate([batch_y, batch_y_2], 1)

                ## Update D network five times
                for _ in range(5):
                    batch_z = np.random.uniform(-1, 1, [self.batch_size, self.z_dim]).astype(np.float32)
                    ## random select texts as "wrong" texts
                    batch_y_random = [self.tags[random_idx] for random_idx in np.random.choice(self.file_names, self.batch_size)]
                    ## 2017/05/23:
                    ## (Special test) if y_dim == 9600
                    ## ==> Use self.tags to read hair vectors and self.tags_sp to read eyes vectors
                    if self.y_dim == 9600:
                        batch_y_random_2 = [self.tags_sp[random_idx] for random_idx in np.random.choice(self.file_names, self.batch_size)]
                        batch_y_random_2 = np.array(batch_y_random_2).astype(np.float32)
                        batch_y_random = np.array(batch_y_random).astype(np.float32)
                        batch_y_random = np.concatenate([batch_y_random, batch_y_random_2], 1)
                    _, summary_str = self.sess.run([d_optim, self.d_sum],
                        feed_dict={ self.inputs: batch_images, self.z: batch_z, \
                                    self.y: batch_y, self.y_random: batch_y_random })
                    self.writer.add_summary(summary_str, counter)

                # Update G network once
                batch_z = np.random.uniform(-1, 1, [self.batch_size, self.z_dim]).astype(np.float32)
                _, summary_str = self.sess.run([g_optim, self.g_sum],
                    feed_dict={ self.z: batch_z, self.y: batch_y })
                self.writer.add_summary(summary_str, counter)
                
                errD_fake = self.d_loss_fake.eval({ self.z: batch_z, self.y: batch_y })
                errD_real = self.d_loss_real.eval({ self.inputs: batch_images, self.y: batch_y })
                errD_wrong = self.d_loss_wrong.eval({ self.inputs: batch_images, self.y_random: batch_y_random })
                errD_ddx = self.ddx.eval({ self.inputs: batch_images, self.z: batch_z, self.y: batch_y })
                errG = self.g_loss.eval({self.z: batch_z, self.y: batch_y})

                counter += 1
                print("Epoch: [%2d] [%4d/%4d] time: %4.4f, d_loss: %.8f, g_loss: %.8f" \
                    % (epoch, idx, batch_idxs, time.time() - start_time, errD_real-errD_fake-errD_wrong-errD_ddx, errG))
                errD_list.append(errD_real-errD_fake-errD_wrong-errD_ddx)
                errG_list.append(errG)

                if np.mod(counter, 200) == 1:
                    try:
                        samples, d_loss, g_loss = self.sess.run(
                            [self.sampler, self.d_loss, self.g_loss],
                                feed_dict={ self.z: sample_z,
                                            self.inputs: sample_inputs,
                                            self.y: batch_y,
                                            self.y_random: batch_y_random})
                        manifold_h = int(np.ceil(np.sqrt(samples.shape[0])))
                        manifold_w = int(np.floor(np.sqrt(samples.shape[0])))
                        save_images(samples, [manifold_h, manifold_w],
                                    './{}/train_{:02d}_{:04d}.png'.format(self.temp_samples_dir, epoch, idx))
                        print("[Sample] d_loss: %.8f, g_loss: %.8f" % (d_loss, g_loss)) 
                    except:
                        print("one pic error!...")
                
                if np.mod(counter, 500) == 2:
                    self.save(self.save_dir, counter)
                    ## Overwrite
                    cPickle.dump(errD_list, open(os.path.join(self.save_dir, 'errD_list.pkl'), 'wb'))
                    cPickle.dump(errG_list, open(os.path.join(self.save_dir, 'errG_list.pkl'), 'wb'))

    def discriminator(self, image, y=None, reuse=False):
        with tf.variable_scope("discriminator") as scope:
            if reuse:
                scope.reuse_variables()
            h0 = lrelu(conv2d(image, self.df_dim, name='d_h0_conv'))            ## h0: [-1, 32, 32, df_dim]
            h1 = lrelu(self.d_bn1(conv2d(h0, self.df_dim*2, name='d_h1_conv')))  ## h1: [-1, 16, 16, df_dim*2]
            h2 = lrelu(self.d_bn2(conv2d(h1, self.df_dim*4, name='d_h2_conv')))  ## h2: [-1, 8, 8, df_dim*4]
            h3 = lrelu(self.d_bn3(conv2d(h2, self.df_dim*8, name='d_h3_conv')))  ## h3: [-1, 4, 4, df_dim*8]
            if self.y_dim == 9600:
                ## Splits y into 2 tensors along axis 1: [batch_size, 9600] ==> [batch_size , 4800], [batch_size , 4800]
                y_hair, y_eyes = tf.split(y, 2, 1)
                yb_hair = lrelu(linear(y_hair, self.t_dim // 2, 'd_hair_embedding'))
                yb_eyes = lrelu(linear(y_eyes, self.t_dim // 2, 'd_eyes_embedding'))
                yb = concat([yb_hair, yb_eyes], 1)
            else:
                yb = lrelu(linear(y, self.t_dim, 'd_embedding'))
            yb = tf.expand_dims(yb,1)
            yb = tf.expand_dims(yb,2)
            yb = tf.tile(yb, [1,4,4,1], name='tiled_embeddings')
            h3_concat = concat([h3, yb], 3, name='h3_concat')
            h3_new = lrelu(self.d_bn4(conv2d(h3_concat, self.df_dim*8, 1,1,1,1, \
                name = 'd_h3_conv_new'))) ## h3_new: [-1, 4, 4, df_dim*8]
            h4 = linear(tf.reshape(h3_new, [self.batch_size, -1]), 1, 'd_h3_lin')
            return h4
    def generator(self, z, y=None):
        with tf.variable_scope("generator") as scope:
            s_h, s_w = self.output_height, self.output_width                        ## 64, 64
            s_h2, s_w2 = conv_out_size_same(s_h, 2), conv_out_size_same(s_w, 2)     ## 32, 32
            s_h4, s_w4 = conv_out_size_same(s_h2, 2), conv_out_size_same(s_w2, 2)   ## 16, 16
            s_h8, s_w8 = conv_out_size_same(s_h4, 2), conv_out_size_same(s_w4, 2)   ## 8, 8
            s_h16, s_w16 = conv_out_size_same(s_h8, 2), conv_out_size_same(s_w8, 2) ## 4, 4
            if self.y_dim == 9600:
                ## Splits y into 2 tensors along axis 1: [batch_size, 9600] ==> [batch_size , 4800], [batch_size , 4800]
                y_hair, y_eyes = tf.split(y, 2, 1)
                yb_hair = lrelu(linear(y_hair, self.t_dim // 2, 'g_hair_embedding'))
                yb_eyes = lrelu(linear(y_eyes, self.t_dim // 2, 'g_eyes_embedding'))
                yb = concat([yb_hair, yb_eyes], 1)
            else:
                yb = lrelu(linear(y, self.t_dim, 'g_embedding'))
            z = concat([z, yb], 1)
            z_ = linear(z, self.gf_dim*8*s_h16*s_w16, 'g_h0_lin')
            h0 = tf.reshape(z_, [-1, s_h16, s_w16, self.gf_dim*8])
            h0 = tf.nn.relu(self.g_bn0(h0))
            h1 = deconv2d(h0, [self.batch_size, s_h8, s_w8, self.gf_dim*4], name='g_h1')
            h1 = tf.nn.relu(self.g_bn1(h1))
            h2 = deconv2d(h1, [self.batch_size, s_h4, s_w4, self.gf_dim*2], name='g_h2')
            h2 = tf.nn.relu(self.g_bn2(h2))
            h3 = deconv2d(h2, [self.batch_size, s_h2, s_w2, self.gf_dim*1], name='g_h3')
            h3 = tf.nn.relu(self.g_bn3(h3))
            h4 = deconv2d(h3, [self.batch_size, s_h, s_w, self.c_dim], name='g_h4')
            return (tf.tanh(h4)/2. + 0.5)

    def sampler(self, z, y=None):
        with tf.variable_scope("generator") as scope:
            scope.reuse_variables()
            s_h, s_w = self.output_height, self.output_width                        ## 64, 64
            s_h2, s_w2 = conv_out_size_same(s_h, 2), conv_out_size_same(s_w, 2)     ## 32, 32
            s_h4, s_w4 = conv_out_size_same(s_h2, 2), conv_out_size_same(s_w2, 2)   ## 16, 16
            s_h8, s_w8 = conv_out_size_same(s_h4, 2), conv_out_size_same(s_w4, 2)   ## 8, 8
            s_h16, s_w16 = conv_out_size_same(s_h8, 2), conv_out_size_same(s_w8, 2) ## 4, 4
            if self.y_dim == 9600:
                ## Splits y into 2 tensors along axis 1: [batch_size, 9600] ==> [batch_size , 4800], [batch_size , 4800]
                y_hair, y_eyes = tf.split(y, 2, 1)
                yb_hair = lrelu(linear(y_hair, self.t_dim // 2, 'g_hair_embedding'))
                yb_eyes = lrelu(linear(y_eyes, self.t_dim // 2, 'g_eyes_embedding'))
                yb = concat([yb_hair, yb_eyes], 1)
            else:
                yb = lrelu(linear(y, self.t_dim, 'g_embedding'))
            z = concat([z, yb], 1)
            z_ = linear(z, self.gf_dim*8*s_h16*s_w16, 'g_h0_lin')
            h0 = tf.reshape(z_, [-1, s_h16, s_w16, self.gf_dim*8])
            h0 = tf.nn.relu(self.g_bn0(h0, train=False))
            h1 = deconv2d(h0, [self.batch_size, s_h8, s_w8, self.gf_dim*4], name='g_h1')
            h1 = tf.nn.relu(self.g_bn1(h1, train=False))
            h2 = deconv2d(h1, [self.batch_size, s_h4, s_w4, self.gf_dim*2], name='g_h2')
            h2 = tf.nn.relu(self.g_bn2(h2, train=False))
            h3 = deconv2d(h2, [self.batch_size, s_h2, s_w2, self.gf_dim*1], name='g_h3')
            h3 = tf.nn.relu(self.g_bn3(h3, train=False))
            h4 = deconv2d(h3, [self.batch_size, s_h, s_w, self.c_dim], name='g_h4')
            return (tf.tanh(h4)/2. + 0.5)
