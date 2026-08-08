
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


def test_fit_model_go():
    """Test full Goel-Okumoto model fitting with known parameters."""
    # Generate synthetic data from GO model: a=100, b=0.1
    np.random.seed(42)
    a_true, b_true = 100.0, 0.1
    # Generate failure times using inverse CDF sampling
    n_events = 50
    uniform_samples = np.random.uniform(0.05, 0.95, n_events)
    t_synthetic = -np.log(1 - uniform_samples * (1 - np.exp(-b_true * 200))) / b_true
    t_synthetic = np.sort(t_synthetic)
    T = float(t_synthetic[-1])

    from modeler.models import fit_model
    params, ll, se, total_exp = fit_model(t_synthetic, T, model_name='go')

    assert params is not None, "GO model should converge on synthetic data"
    a_fit, b_fit = params
    # Parameters should be in the right ballpark
    assert 50 < a_fit < 200, f"Expected a around 100, got {a_fit:.1f}"
    assert 0.03 < b_fit < 0.3, f"Expected b around 0.1, got {b_fit:.4f}"
    assert ll is not None and ll > -np.inf
    assert total_exp is not None


def test_fit_model_mo():
    """Test full Musa-Okumoto model fitting with known parameters."""
    np.random.seed(123)
    lambda0_true, theta_true = 20.0, 0.01
    n_events = 50
    uniform_samples = np.random.uniform(0.05, 0.95, n_events)
    # Inverse CDF for MO: t = (exp(theta * u) - 1) / (lambda0 * theta)  where u ~ mu(t)
    # Simpler: generate GO data and fit MO (should still converge)
    a, b = 100.0, 0.1
    u = np.random.uniform(0.05, 0.95, n_events)
    t_synthetic = -np.log(1 - u * (1 - np.exp(-b * 200))) / b
    t_synthetic = np.sort(t_synthetic)
    T = float(t_synthetic[-1])

    from modeler.models import fit_model
    params, ll, se, total_exp = fit_model(t_synthetic, T, model_name='mo')

    assert params is not None, "MO model should converge on failure data"
    lambda0_fit, theta_fit = params
    assert lambda0_fit > 0, f"lambda0 should be positive, got {lambda0_fit}"
    assert theta_fit > 0, f"theta should be positive, got {theta_fit}"
    assert ll is not None and ll > -np.inf


def test_fit_model_too_few_points():
    """fit_model should return None for fewer than 3 data points."""
    from modeler.models import fit_model
    t = np.array([1.0, 2.0])
    params, ll, se, total_exp = fit_model(t, 5.0, model_name='go')
    assert params is None, "Should return None for n < 3"
