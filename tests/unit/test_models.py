
import pytest
import numpy as np
from modeler.models import go_mu, mo_mu, go_loglik

def test_go_mu():
    # Test Goel-Okumoto mean value function
    # mu(t) = a * (1 - exp(-b*t))
    a = 100
    b = 0.1
    t = 10
    expected = 100 * (1 - np.exp(-1))
    assert np.isclose(go_mu(t, [a, b]), expected)

    # t=0 should be 0
    assert go_mu(0, [a, b]) == 0

    # t -> infinity should be a
    assert np.isclose(go_mu(10000, [a, b]), a, atol=0.1)

def test_mo_mu():
    # Test Musa-Okumoto mean value function
    # mu(t) = (1/theta) * log(1 + lambda0 * theta * t)
    lambda0 = 10
    theta = 0.01
    t = 10
    expected = (1/theta) * np.log(1 + lambda0 * theta * t)
    assert np.isclose(mo_mu(t, [lambda0, theta]), expected)

    # t=0 should be 0
    assert mo_mu(0, [lambda0, theta]) == 0

def test_go_loglik_invalid_params():
    # Log likelihood should return -inf for invalid parameters
    t = np.array([1, 2, 3])
    T = 5
    assert go_loglik([-10, 0.1], t, T) == -np.inf
    assert go_loglik([100, -0.1], t, T) == -np.inf
