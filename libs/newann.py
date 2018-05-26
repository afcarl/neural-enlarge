from keras import backend as K
import os
from libs.version import __version__
from libs.args import args
from libs.console import error, extend, ansi
import numpy as nd
import collections
from keras.models import Model as KerasModel
from keras.layers import Input, Conv2D, Conv2DTranspose, Add, UpSampling2D, MaxPooling2D, Convolution2D, MaxPool2D
from keras import optimizers
import numpy as np

import tensorflow as tf
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'


def psnr(y_true, y_pred):
    assert y_true.shape == y_pred.shape, "Cannot calculate PSNR. Input shapes not same." \
                                         " y_true shape = %s, y_pred shape = %s" % (str(y_true.shape),
                                                                                   str(y_pred.shape))

    return -10. * np.log10(np.mean(np.square(y_pred - y_true)))


def PSNRLoss(y_true, y_pred):
    """
    PSNR is Peek Signal to Noise Ratio, which is similar to mean squared error.

    It can be calculated as
    PSNR = 20 * log10(MAXp) - 10 * log10(MSE)

    When providing an unscaled input, MAXp = 255. Therefore 20 * log10(255)== 48.1308036087.
    However, since we are scaling our input, MAXp = 1. Therefore 20 * log10(1) = 0.
    Thus we remove that component completely and only compute the remaining MSE component.
    """
    return -10. * K.log(K.mean(K.square(y_pred - y_true))) / K.log(10.)


class Model(object):

    def __init__(self):
        self.network = collections.OrderedDict()
        self.history = None
        self.model = None
        self.channels = 3

        self.n1 = 64
        self.n2 = 128
        self.n3 = 256

        self.load_model()

    def make_model(self):
        img_size = args.batch_shape / 2
        init = Input((img_size, img_size, 3), name='input_1')
        c1 = Conv2D(self.n1, (3, 3), activation='relu', padding='same')(init)
        c1 = Conv2D(self.n1, (3, 3), activation='relu', padding='same')(c1)

        # upsample the output feeding m2
        # c1_up = UpSampling2D()(c1)
        c1_up = Conv2DTranspose(self.n1, (3, 3), activation='relu', padding='same', strides=(2, 2))(c1)


        # don't pool so we can upscale
        # x = MaxPooling2D((2, 2))(c1)
        x = c1

        c2 = Conv2D(self.n2, (3, 3), activation='relu', padding='same')(x)
        c2 = Conv2D(self.n2, (3, 3), activation='relu', padding='same')(c2)

        x = MaxPooling2D((2, 2))(c2)

        c3 = Conv2D(self.n3, (3, 3), activation='relu', padding='same')(x)

        # x = UpSampling2D()(c3)
        x = Conv2DTranspose(self.n3, (3, 3), activation='relu', padding='same', strides=(2, 2))(c3)

        c2_2 = Conv2D(self.n2, (3, 3), activation='relu', padding='same')(x)
        c2_2 = Conv2D(self.n2, (3, 3), activation='relu', padding='same')(c2_2)

        m1 = Add()([c2, c2_2])
        m1 = Conv2DTranspose(self.n1, (3, 3), activation='relu', padding='same', strides=(2, 2))(m1)
        # m1 = UpSampling2D()(m1)

        c1_2 = Conv2D(self.n1, (3, 3), activation='relu', padding='same')(m1)
        c1_2 = Conv2D(self.n1, (3, 3), activation='relu', padding='same')(c1_2)

        m2 = Add()([c1_up, c1_2])

        decoded = Conv2D(self.channels, (5, 5), activation='linear', padding='same')(m2)

        model = KerasModel(init, decoded)
        adam = optimizers.Adam(lr=1e-3)
        model.compile(optimizer=adam, loss='mse', metrics=[PSNRLoss])

        model.summary()

        # load weights
        if os.path.exists(self.get_filename(absolute=True)):
            model.load_weights(self.get_filename(absolute=True), by_name=True)
        self.model = model

        # return model

    def fit(self, images, seeds):
        # print('fitting')
        # self.history = self.model.fit(seeds, images, verbose=0, epochs=1, validation_split=.2)
        # print('seeds', seeds.shape)
        # print('images', images.shape)
        self.history = self.model.train_on_batch(seeds, images)
        # return self.history.history
        # print(self.history)
        return self.history

    def get_filename(self, absolute=False):
        filename = 'models/ne%ix-%s-%s-%s.h5' % (args.zoom, args.type, args.model, __version__)
        return os.path.abspath(filename) if absolute else filename

    def save(self):
        self.model.save(self.get_filename(absolute=True))

    def load_model(self):
        if not os.path.exists(self.get_filename(absolute=True)):
            if args.train:
                self.make_model()
            else:
                error("Model file with pre-trained convolution layers not found. Download it here...",
                      "https://github.com/jaretburkett/neural-enlarge/releases/download/v%s/%s" % (
                          __version__, self.get_filename()))
        else:
            print('Importing weights from file %s' % self.get_filename(absolute=False))
            self.make_model()

    def set_learning_rate(self, lr):
        K.set_value(self.model.optimizer.lr, lr)

    def predict(self, img_arr):
        scald = []
        repro = []
        for x in img_arr:
            scald.append(x)
            training_seeds = np.transpose(x, (2, 1, 0))
            processed = self.model.predict(nd.array([training_seeds]))
            repro.append(processed[0])

        return scald, repro


