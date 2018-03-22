from __future__ import absolute_import, division, print_function

from keras import backend as k
from keras.utils.generic_utils import Progbar

import numpy as np
import tensorflow as tf

from src.attacks.attack import Attack, class_derivative


class NewtonFool(Attack):
    """
    Implementation of the attack from Uyeong Jang et al. (2017).
    Paper link: http://doi.acm.org/10.1145/3134600.3134635
    """
    attack_params = ["max_iter", "eta", "verbose"]

    def __init__(self, classifier, sess, max_iter=100, eta=0.01, verbose=1):
        """
        Create a NewtonFool attack instance.
        :param classifier: An object of classifier.
        :param sess: The tf session to run graphs in.
        :param max_iter: (integer) The maximum number of iterations.
        :param eta: (float) The eta coefficient.
        :param verbose: (optional boolean)
        """
        super(NewtonFool, self).__init__(classifier, sess)
        params = {"max_iter": max_iter, "eta": eta, "verbose": verbose}
        self.set_params(**params)

    def generate(self, x_val, **kwargs):
        """
        Generate adversarial samples and return them in a Numpy array.
        :param x_val: (required) A Numpy array with the original inputs.
        :return: A Numpy array holding the adversarial examples.
        """
        assert self.set_params(**kwargs)
        dims = list(x_val.shape)
        dims[0] = None
        nb_classes = self.model.output_shape[1]
        xi_op = tf.placeholder(dtype=tf.float32, shape=dims)
        loss = self.classifier.model(xi_op)
        grads_graph = class_derivative(loss, xi_op, nb_classes)
        x_adv = x_val.copy()

        # Progress bar
        progress_bar = Progbar(target=len(x_val), verbose=self.verbose)

        # Initialize variables
        y_pred = self.classifier.model.predict(x_val)
        pred_class = np.argmax(y_pred, axis=1)

        # Main algorithm for each example
        for j, x in enumerate(x_adv):
            xi = x[None, ...]
            norm_x0 = np.linalg.norm(np.reshape(x, [-1]))
            l = pred_class[j]
            #d = np.zeros(shape=dims[1:])

            # Main loop of the algorithm
            for i in range(self.max_iter):
                # Compute score
                score = self.classifier.model.predict(xi)[0][l]

                # Compute the gradients and norm
                grads = self.sess.run(grads_graph, feed_dict={xi_op: xi})[l][0]
                norm_grad = np.linalg.norm(np.reshape(grads, [-1]))

                # Theta
                theta = self._compute_theta(norm_x0, score, norm_grad,
                                            nb_classes)

                # Pertubation
                di = self._compute_pert(theta, grads, norm_grad)

                # Update xi and pertubation
                xi += di
                #d += di

            # Return the adversarial example
            x_adv[j] = xi[0]
            progress_bar.update(current=j, values=[("perturbation", abs(
                np.linalg.norm((x_adv[j] - x_val[j]).flatten())))])

        return x_adv

    def set_params(self, **kwargs):
        """Take in a dictionary of parameters and applies attack-specific
        checks before saving them as attributes.

        Attack-specific parameters:
        :param max_iter: (integer) The maximum number of iterations.
        :param eta: (float) The eta coefficient.
        :param verbose: (optional boolean)
        """
        # Save attack-specific parameters
        super(NewtonFool, self).set_params(**kwargs)

        if type(self.max_iter) is not int or self.max_iter <= 0:
            raise ValueError("The number of iterations must be a "
                             "positive integer.")

        if type(self.eta) is not float or self.eta <= 0:
            raise ValueError("The eta coefficient must be a positive float.")

        return True

    def _compute_theta(self, norm_x0, score, norm_grad, nb_classes):
        """
        Function to compute the theta at each step.
        :param norm_x0: norm of x0
        :param score: softmax value at the attacked class.
        :param norm_grad: norm of gradient values at the attacked class.
        :param nb_classes: number of classes.
        :return: theta value.
        """
        equ1 = self.eta * norm_x0 * norm_grad
        equ2 = score - 1.0/nb_classes
        result = min(equ1, equ2)

        return result

    def _compute_pert(self, theta, grads, norm_grad):
        """
        Function to compute the pertubation at each step.
        :param theta: theta value at the current step.
        :param grads: gradient values at the attacked class.
        :param norm_grad: norm of gradient values at the attacked class.
        :return: pertubation.
        """
        nom = -theta * grads
        denom = norm_grad**2
        result = nom / float(denom)

        return result


