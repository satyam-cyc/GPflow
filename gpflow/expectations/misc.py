import tensorflow as tf

from . import dispatch
from .. import kernels
from .. import mean_functions as mfn
from ..features import InducingFeature, InducingPoints
from ..probability_distributions import (DiagonalGaussian, Gaussian,
                                         MarkovGaussian)
from ..util import NoneType
from .expectations import expectation

# ================ exKxz transpose and mean function handling =================


@dispatch.expectation.register((Gaussian, MarkovGaussian),
                               mfn.Identity, NoneType,
                               kernels.Linear, InducingPoints)
def _E(p, mean, _, kern, feat, nghp=None):
    """
    Compute the expectation:
    expectation[n] = <x_n K_{x_n, Z}>_p(x_n)
        - K_{.,} :: Linear kernel
    or the equivalent for MarkovGaussian

    :return: NxDxM
    """
    return tf.linalg.transpose(expectation(p, (kern, feat), mean))


@dispatch.expectation.register((Gaussian, MarkovGaussian),
                               kernels.Kernel, InducingFeature,
                               mfn.MeanFunction, NoneType)
def _E(p, kern, feat, mean, _, nghp=None):
    """
    Compute the expectation:
    expectation[n] = <K_{Z, x_n} m(x_n)>_p(x_n)
    or the equivalent for MarkovGaussian

    :return: NxMxQ
    """
    return tf.linalg.transpose(expectation(p, mean, (kern, feat), nghp=nghp))


@dispatch.expectation.register(Gaussian, mfn.Constant, NoneType, kernels.Kernel, InducingPoints)
def _E(p, constant_mean, _, kern, feat, nghp=None):
    """
    Compute the expectation:
    expectation[n] = <m(x_n)^T K_{x_n, Z}>_p(x_n)
        - m(x_i) = c :: Constant function
        - K_{.,.}    :: Kernel function

    :return: NxQxM
    """
    c = constant_mean(p.mu)  # NxQ
    eKxz = expectation(p, (kern, feat), nghp=nghp)  # NxM

    return c[..., None] * eKxz[:, None, :]


@dispatch.expectation.register(Gaussian, mfn.Linear, NoneType, kernels.Kernel, InducingPoints)
def _E(p, linear_mean, _, kern, feat, nghp=None):
    """
    Compute the expectation:
    expectation[n] = <m(x_n)^T K_{x_n, Z}>_p(x_n)
        - m(x_i) = A x_i + b :: Linear mean function
        - K_{.,.}            :: Kernel function

    :return: NxQxM
    """
    N = p.mu.shape[0]
    D = p.mu.shape[1]
    exKxz = expectation(p, mfn.Identity(D), (kern, feat), nghp=nghp)
    eKxz = expectation(p, (kern, feat), nghp=nghp)
    eAxKxz = tf.linalg.matmul(tf.tile(linear_mean.A[None, :, :], (N, 1, 1)), exKxz,
                              transpose_a=True)
    ebKxz = linear_mean.b[None, :, None] * eKxz[:, None, :]
    return eAxKxz + ebKxz


@dispatch.expectation.register(Gaussian, mfn.Identity, NoneType, kernels.Kernel, InducingPoints)
def _E(p, identity_mean, _, kern, feat, nghp=None):
    """
    This prevents infinite recursion for kernels that don't have specific
    implementations of _expectation(p, identity_mean, None, kern, feat).
    Recursion can arise because Identity is a subclass of Linear mean function
    so _expectation(p, linear_mean, none, kern, feat) would call itself.
    More specific signatures (e.g. (p, identity_mean, None, RBF, feat)) will
    be found and used whenever available
    """
    raise NotImplementedError


# ============== Conversion to Gaussian from Diagonal or Markov ===============
# Catching missing DiagonalGaussian implementations by converting to full Gaussian:


@dispatch.expectation.register(DiagonalGaussian,
                               object, (InducingFeature, NoneType),
                               object, (InducingFeature, NoneType))
def _E(p, obj1, feat1, obj2, feat2, nghp=None):
    gaussian = Gaussian(p.mu, tf.linalg.diag(p.cov))
    return expectation(gaussian, (obj1, feat1), (obj2, feat2), nghp=nghp)


# Catching missing MarkovGaussian implementations by converting to Gaussian (when indifferent):

@dispatch.expectation.register(MarkovGaussian,
                               object, (InducingFeature, NoneType),
                               object, (InducingFeature, NoneType))
def _E(p, obj1, feat1, obj2, feat2, nghp=None):
    """
    Nota Bene: if only one object is passed, obj1 is
    associated with x_n, whereas obj2 with x_{n+1}

    """
    if obj2 is None:
        gaussian = Gaussian(p.mu[:-1], p.cov[0, :-1])
        return expectation(gaussian, (obj1, feat1), nghp=nghp)
    elif obj1 is None:
        gaussian = Gaussian(p.mu[1:], p.cov[0, 1:])
        return expectation(gaussian, (obj2, feat2), nghp=nghp)
    else:
        return expectation(p, (obj1, feat1), (obj2, feat2), nghp=nghp)
