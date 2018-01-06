# ---------------------------------------------------------#
#   astroNN.models.models_shared: Shared across models
# ---------------------------------------------------------#
import os
import sys
from abc import ABC, abstractmethod
import time

import keras
import keras.backend as K
import keras.losses
import numpy as np
import tensorflow as tf
from keras.optimizers import Adam
from keras.utils import plot_model
from tensorflow.contrib import distributions
from tensorflow.python.client import device_lib

import astroNN
from astroNN.shared.nn_tools import folder_runnum, cpu_fallback, gpu_memory_manage

K.set_learning_phase(1)


class ModelStandard(ABC):
    """
    NAME:
        ModelStandard
    PURPOSE:
        To define astroNN standard model
    HISTORY:
        2017-Dec-23 - Written - Henry Leung (University of Toronto)
    """

    def __init__(self):
        keras.losses.custom_loss = self.mse_var_wrapper

        self.name = None
        self._model_type = None
        self._implementation_version = None
        self.__python_info = sys.version
        self.__astronn_ver = astroNN.__version__
        self.__keras_ver = keras.__version__
        self.__tf_ver = tf.__version__
        self.runnum_name = None
        self.batch_size = None
        self.initializer = None
        self.input_shape = None
        self.activation = None
        self.num_filters = 'N/A'
        self.filter_length = 'N/A'
        self.pool_length = 'N/A'
        self.num_hidden = None
        self.output_shape = None
        self.optimizer = None
        self.max_epochs = None
        self.latent_dim = 'N/A'
        self.lr = None
        self.reduce_lr_epsilon = None
        self.reduce_lr_min = None
        self.reduce_lr_patience = None
        self.fallback_cpu = False
        self.limit_gpu_mem = True
        self.data_normalization = True
        self.target = None
        self.currentdir = os.getcwd()
        self.fullfilepath = None
        self.task = 'regression'  # Either 'regression' or 'classification'
        self.keras_model = None
        self.inv_model_precision = None

        self.beta_1 = 0.9  # exponential decay rate for the 1st moment estimates for optimization algorithm
        self.beta_2 = 0.999  # exponential decay rate for the 2nd moment estimates for optimization algorithm
        self.optimizer_epsilon = K.epsilon()  # a small constant for numerical stability for optimization algorithm

    def hyperparameter_writer(self):
        with open(self.fullfilepath + 'hyperparameter.txt', 'w') as h:
            h.write("model: {} \n".format(self.name))
            h.write("astroNN internal identifier: {} \n".format(self._model_type))
            h.write("model version: {} \n".format(self._implementation_version))
            h.write("python version: {} \n".format(self.__python_info))
            h.write("astroNN version: {} \n".format(self.__astronn_ver))
            h.write("keras version: {} \n".format(self.__keras_ver))
            h.write("tensorflow version: {} \n".format(self.__tf_ver))
            h.write("runnum_name: {} \n".format(self.runnum_name))
            h.write("batch_size: {} \n".format(self.batch_size))
            h.write("initializer: {} \n".format(self.initializer))
            h.write("input_shape: {} \n".format(self.input_shape))
            h.write("activation: {} \n".format(self.activation))
            h.write("num_filters: {} \n".format(self.num_filters))
            h.write("filter_length: {} \n".format(self.filter_length))
            h.write("pool_length: {} \n".format(self.pool_length))
            h.write("num_hidden: {} \n".format(self.num_hidden))
            h.write("output_shape: {} \n".format(self.output_shape))
            h.write("optimizer: {} \n".format(self.optimizer))
            h.write("max_epochs: {} \n".format(self.max_epochs))
            h.write("latent dimension: {} \n".format(self.latent_dim))
            h.write("lr: {} \n".format(self.lr))
            h.write("reduce_lr_epsilon: {} \n".format(self.reduce_lr_epsilon))
            h.write("reduce_lr_min: {} \n".format(self.reduce_lr_min))
            h.write("reduce_lr_patience: {} \n".format(self.reduce_lr_patience))
            h.write("fallback cpu? : {} \n".format(self.fallback_cpu))
            h.write("astroNN GPU management: {} \n".format(self.limit_gpu_mem))
            h.write("astroNN data normalizing implementation? : {} \n".format(self.data_normalization))
            h.write("target? : {} \n".format(self.target))
            h.write("currentdir: {} \n".format(self.currentdir))
            h.write("fullfilepath: {} \n".format(self.fullfilepath))
            h.write("neural task: {} \n".format(self.task))
            h.write("\n")
            h.write("============Tensorflow diagnostic============\n")
            h.write("{} \n".format(device_lib.list_local_devices()))
            h.write("============Tensorflow diagnostic============\n")
            h.write("\n")

            h.close()

            astronn_internal_path = os.path.join(self.fullfilepath, 'astroNN_use_only')
            os.makedirs(astronn_internal_path)

            np.save(astronn_internal_path + '/astroNN_identifier.npy', self._model_type)
            np.save(astronn_internal_path + '/input.npy', self.input_shape)
            np.save(astronn_internal_path + '/output.npy', self.output_shape)
            np.save(astronn_internal_path + '/hidden.npy', self.num_hidden)
            np.save(astronn_internal_path + '/filternum.npy', self.num_filters)
            np.save(astronn_internal_path + '/filterlen.npy', self.filter_length)
            np.save(astronn_internal_path + '/task.npy', self.task)
            if self.latent_dim is not None or self.latent_dim != 'N/A':
                np.save(astronn_internal_path + '/latent.npy', self.latent_dim)

    @staticmethod
    def mean_squared_error(y_true, y_pred):
        return K.mean(K.tf.where(K.tf.equal(y_true, -9999.), K.tf.zeros_like(y_true), K.square(y_true - y_pred)),
                      axis=-1)

    @staticmethod
    def mse_var_wrapper(lin):
        def mse_var(y_true, y_pred):
            wrapper_output = K.tf.where(K.tf.equal(y_true, -9999.), K.tf.zeros_like(y_true),
                                        0.5 * K.square(y_true - lin) * (K.exp(-y_pred)) + 0.5 * y_pred)
            return K.mean(wrapper_output, axis=-1)

        return mse_var

    @staticmethod
    def categorical_cross_entropy(y_true, y_pred):
        return K.sum(K.switch(K.equal(y_true, -9999.), K.tf.zeros_like(y_true), y_true * np.log(y_pred)), axis=-1)

    @staticmethod
    def gaussian_crossentropy(true, pred, dist, undistorted_loss, num_classes):
        # for a single monte carlo simulation,
        #   calculate categorical_crossentropy of
        #   predicted logit values plus gaussian
        #   noise vs true values.
        # true - true values. Shape: (N, C)
        # pred - predicted logit values. Shape: (N, C)
        # dist - normal distribution to sample from. Shape: (N, C)
        # undistorted_loss - the crossentropy loss without variance distortion. Shape: (N,)
        # num_classes - the number of classes. C
        # returns - total differences for all classes (N,)
        def map_fn(i):
            std_samples = K.transpose(dist.sample(num_classes))
            distorted_loss = K.categorical_crossentropy(pred + std_samples, true, from_logits=True)
            diff = undistorted_loss - distorted_loss
            return -K.elu(diff)

        return map_fn

    def bayes_crossentropy_wrapper(self, T, num_classes):
        # Bayesian categorical cross entropy.
        # N data points, C classes, T monte carlo simulations
        # true - true values. Shape: (N, C)
        # pred_var - predicted logit values and variance. Shape: (N, C + 1)
        # returns - loss (N,)
        def bayes_crossentropy(true, pred_var):
            # shape: (N,)
            std = K.sqrt(pred_var[:, num_classes:])
            # shape: (N,)
            variance = pred_var[:, num_classes]
            variance_depressor = K.exp(variance) - K.ones_like(variance)
            # shape: (N, C)
            pred = pred_var[:, 0:num_classes]
            # shape: (N,)
            undistorted_loss = K.categorical_crossentropy(pred, true, from_logits=True)
            # shape: (T,)
            iterable = K.variable(np.ones(T))
            dist = distributions.Normal(loc=K.zeros_like(std), scale=std)
            monte_carlo_results = K.map_fn(
                self.gaussian_crossentropy(true, pred, dist, undistorted_loss, num_classes), iterable,
                name='monte_carlo_results')

            variance_loss = K.mean(monte_carlo_results, axis=0) * undistorted_loss

            return variance_loss + undistorted_loss + variance_depressor

        return bayes_crossentropy

    def pre_training_checklist(self, x_train, y_train):
        if self.fallback_cpu is True:
            cpu_fallback()

        if self.limit_gpu_mem is not False:
            gpu_memory_manage()

        if self.task != 'regression' and self.task != 'classification':
            raise RuntimeError("task can only either be 'regression' or 'classification'. ")

        self.runnum_name = folder_runnum()
        self.fullfilepath = os.path.join(self.currentdir, self.runnum_name + '/')

        if self.optimizer is None or self.optimizer == 'adam':
            self.optimizer = Adam(lr=self.lr, beta_1=self.beta_1, beta_2=self.beta_2, epsilon=self.optimizer_epsilon,
                                  decay=0.0)

        x_train_norm, y_train_norm = np.array(x_train), np.array(y_train)

        if self.data_normalization is True:

            # do not include -9999 in mean and std calculation and do not normalize those elements because
            # astroNN is designed to ignore -9999. only
            mean_labels = np.zeros(y_train_norm.shape[1])
            std_labels = np.ones(y_train_norm.shape[1])
            for i in range(y_train_norm.shape[1]):
                not9999 = np.where(y_train_norm[:, i] != -9999.)[0]
                mean_labels[i] = np.mean((y_train_norm[:, i])[not9999], axis=0)
                std_labels[i] = np.std((y_train_norm[:, i])[not9999], axis=0)
                (y_train_norm[:, i])[not9999] -= mean_labels[i]
                (y_train_norm[:, i])[not9999] /= std_labels[i]
            mu_std = np.vstack((mean_labels, std_labels))
            np.save(self.fullfilepath + 'meanstd.npy', mu_std)
            np.save(self.fullfilepath + 'targetname.npy', self.target)

            x_mu_std = np.vstack((np.median(x_train), np.std(x_train)))
            np.save(self.fullfilepath + 'meanstd_x.npy', x_mu_std)

            x_train_norm -= x_mu_std[0]
            x_train_norm /= x_mu_std[1]

        self.input_shape = (x_train_norm.shape[1], 1,)
        self.output_shape = (y_train_norm.shape[1], 1,)

        self.hyperparameter_writer()

        return x_train_norm, y_train_norm

    def model_existence(self):
        if self.keras_model is None:
            try:
                self.keras_model.load_weights(self.fullfilepath + '/model_weights.h5')
            except all:
                raise TypeError('This object contains no model, Please load the model first')

    def plot_model(self):
        try:
            plot_model(self.keras_model, show_shapes=True, to_file=self.fullfilepath + 'model.png')
        except all:
            print('Skipped plot_model! graphviz and pydot_ng are required to plot the model architecture')
            pass

    @abstractmethod
    def model(self):
        pass

    @abstractmethod
    def compile(self):
        pass

    @abstractmethod
    def train(self, x_train, y_train):
        x_train_normalized, y_train_normalized = self.pre_training_checklist(x_train, y_train)
        return x_train_normalized, y_train_normalized

    @abstractmethod
    def test(self, x_test):
        # Prevent shallow copy issue
        x_data = np.array(x_test)

        x_mu_std = np.load(self.fullfilepath + '/meanstd_x.npy')
        x_data -= x_mu_std[0]
        x_data /= x_mu_std[1]
        x_data = np.atleast_3d(x_data)
        self.model_existence()
        return x_data

    def aspcap_residue_plot(self, test_predictions, test_labels, test_pred_error):
        import pylab as plt
        from astroNN.shared.nn_tools import target_name_conversion
        import numpy as np
        import seaborn as sns

        print("Start plotting residues")

        resid = test_predictions - test_labels

        # Some plotting variables for asthetics
        plt.rcParams['axes.facecolor'] = 'white'
        sns.set_style("ticks")
        plt.rcParams['axes.grid'] = True
        plt.rcParams['grid.color'] = 'gray'
        plt.rcParams['grid.alpha'] = '0.4'
        std_labels = np.load(self.fullfilepath + '/meanstd.npy')[1]

        x_lab = 'ASPCAP'
        y_lab = 'astroNN'
        fullname = target_conversion(self.target)

        aspcap_residue_path = os.path.join(self.fullfilepath, 'ASPCAP_residue')

        if not os.path.exists(aspcap_residue_path):
            os.makedirs(aspcap_residue_path)

        for i in range(self.output_shape[0]):
            plt.figure(figsize=(15, 11), dpi=200)
            plt.axhline(0, ls='--', c='k', lw=2)
            not9999 = np.where(test_labels[:, i] != -9999.)[0]
            plt.errorbar((test_labels[:, i])[not9999], (resid[:, i])[not9999], yerr=(test_pred_error[:, i])[not9999],
                         markersize=2, fmt='o', ecolor='g', capthick=2, elinewidth=0.5)

            plt.xlabel('ASPCAP ' + target_name_conversion(fullname[i]), fontsize=25)
            plt.ylabel('$\Delta$ ' + target_name_conversion(fullname[i]) + '\n(' + y_lab + ' - ' + x_lab + ')',
                       fontsize=25)
            plt.tick_params(labelsize=20, width=1, length=10)
            if self.output_shape[0] == 1:
                plt.xlim([np.min((test_labels[:])[not9999]), np.max((test_labels[:])[not9999])])
            else:
                plt.xlim([np.min((test_labels[:, i])[not9999]), np.max((test_labels[:, i])[not9999])])
            ranges = (np.max((test_labels[:, i])[not9999]) - np.min((test_labels[:, i])[not9999])) / 2
            plt.ylim([-ranges, ranges])
            bbox_props = dict(boxstyle="square,pad=0.3", fc="w", ec="k", lw=2)
            bias = np.median((resid[:, i])[not9999])
            scatter = np.std((resid[:, i])[not9999])
            plt.figtext(0.6, 0.75,
                        '$\widetilde{m}$=' + '{0:.3f}'.format(bias) + ' $\widetilde{s}$=' + '{0:.3f}'.format(
                            scatter / float(std_labels[i])) + ' s=' + '{0:.3f}'.format(scatter), size=25, bbox=bbox_props)
            plt.tight_layout()
            plt.savefig(aspcap_residue_path + '/{}_test.png'.format(fullname[i]))
            plt.close('all')
            plt.clf()

        print("Finished plotting residues")

    def jacobian(self, x=None, plotting=True):
        """
        NAME: cal_jacobian
        PURPOSE: calculate jacobian
        INPUT:
        OUTPUT:
        HISTORY:
            2017-Nov-20 Henry Leung
        """
        import pylab as plt
        import numpy as np
        import seaborn as sns
        import matplotlib.ticker as ticker
        from astroNN.apogee.chips import wavelength_solution, chips_split
        from astroNN.shared.nn_tools import aspcap_windows_url_correction
        from urllib.request import urlopen
        import pandas as pd

        if x is None:
            raise ValueError('Please provide data to calculate the jacobian')

        K.set_learning_phase(0)
        dr =14

        # Force to reload model to start a new session
        self.model_existence()
        x = np.atleast_3d(x)
        # enforce float16 because the precision doesnt really matter
        input_tens = self.keras_model.layers[0].input
        jacobian = np.empty((self.output_shape[0], x.shape[0], x.shape[1]), dtype=np.float16)
        start_time = time.time()

        with K.get_session() as sess:
            for counter, j in enumerate(range(self.output_shape[0])):
                print('Completed {} of {} output, {:.03f} seconds elapsed'.format(counter, self.output_shape[0],
                                                                                  time.time() - start_time))
                grad = self.keras_model.layers[-1].output[0, j]
                for i in range(x.shape[0]):
                    jacobian[j, i:i + 1, :] = (np.asarray(sess.run(K.tf.gradients(grad, input_tens),
                                                                   feed_dict={input_tens: x[i:i + 1]})))[:, :, 0].T

            # Some plotting variables for asthetics
            plt.rcParams['axes.facecolor'] = 'white'
            sns.set_style("ticks")
            plt.rcParams['axes.grid'] = False
            plt.rcParams['grid.color'] = 'gray'
            plt.rcParams['grid.alpha'] = '0.4'
            path = os.path.join(self.fullfilepath, 'jacobian')
            if not os.path.exists(path):
                os.makedirs(path)

            fullname = target_conversion(self.target)
            lambda_blue, lambda_green, lambda_red = wavelength_solution(dr=dr)

            for j in range(self.output_shape[0]):
                fig = plt.figure(figsize=(45, 30), dpi=150)
                scale = np.max(np.abs((jacobian[j, :])))
                scale_2 = np.min((jacobian[j, :]))
                blue, green, red = chips_split(jacobian[j, :], dr=dr)
                ax1 = fig.add_subplot(311)
                fig.suptitle('{}, Average of {} Stars'.format(fullname[j], x.shape[0]), fontsize=50)
                ax1.set_ylabel(r'$\partial$' + fullname[j], fontsize=40)
                ax1.set_ylim(scale_2, scale)
                ax1.plot(lambda_blue, blue, linewidth=0.9, label='astroNN')
                ax2 = fig.add_subplot(312)
                ax2.set_ylabel(r'$\partial$' + fullname[j], fontsize=40)
                ax2.set_ylim(scale_2, scale)
                ax2.plot(lambda_green, green, linewidth=0.9, label='astroNN')
                ax3 = fig.add_subplot(313)
                ax3.set_ylim(scale_2, scale)
                ax3.set_ylabel(r'$\partial$' + fullname[j], fontsize=40)
                ax3.plot(lambda_red, red, linewidth=0.9, label='astroNN')
                ax3.set_xlabel(r'Wavelength (Angstrom)', fontsize=40)

                ax1.axhline(0, ls='--', c='k', lw=2)
                ax2.axhline(0, ls='--', c='k', lw=2)
                ax3.axhline(0, ls='--', c='k', lw=2)

                try:
                    if dr == 14:
                        url = "https://svn.sdss.org/public/repo/apogee/idlwrap/trunk/lib/l31c/{}.mask".format(
                            aspcap_windows_url_correction(self.target[j]))
                    else:
                        raise ValueError('Only support DR14')
                    df = np.array(pd.read_csv(urlopen(url), header=None, sep='\t'))
                    print(url)
                    aspcap_windows = df * scale
                    aspcap_blue, aspcap_green, aspcap_red = chips_split(aspcap_windows, dr=dr)
                    ax1.plot(lambda_blue, aspcap_blue, linewidth=0.9, label='ASPCAP windows')
                    ax2.plot(lambda_green, aspcap_green, linewidth=0.9, label='ASPCAP windows')
                    ax3.plot(lambda_red, aspcap_red, linewidth=0.9, label='ASPCAP windows')
                except:
                    print('No ASPCAP windows data for {}'.format(aspcap_windows_url_correction(self.target[j])))
                tick_spacing = 50
                ax1.xaxis.set_major_locator(ticker.MultipleLocator(tick_spacing))
                ax2.xaxis.set_major_locator(ticker.MultipleLocator(tick_spacing / 1.5))
                ax3.xaxis.set_major_locator(ticker.MultipleLocator(tick_spacing / 1.7))
                ax1.minorticks_on()
                ax2.minorticks_on()
                ax3.minorticks_on()

                ax1.tick_params(labelsize=30, width=2, length=20, which='major')
                ax1.tick_params(width=2, length=10, which='minor')
                ax2.tick_params(labelsize=30, width=2, length=20, which='major')
                ax2.tick_params(width=2, length=10, which='minor')
                ax3.tick_params(labelsize=30, width=2, length=20, which='major')
                ax3.tick_params(width=2, length=10, which='minor')
                ax1.legend(loc='best', fontsize=40)
                plt.tight_layout()
                plt.subplots_adjust(left=0.05)
                plt.savefig(path + '/{}_jacobian.png'.format(self.target[j]))
                plt.close('all')
                plt.clf()

        return jacobian


def target_conversion(target):
    if target == 'all' or target == ['all']:
        target = ['teff', 'logg', 'M', 'alpha', 'C', 'C1', 'N', 'O', 'Na', 'Mg', 'Al', 'Si', 'P', 'S', 'K', 'Ca', 'Ti',
                  'Ti2', 'V', 'Cr', 'Mn', 'Fe', 'Co', 'Ni', 'fakemag']
    return np.asarray(target)
