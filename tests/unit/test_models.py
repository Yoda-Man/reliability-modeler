
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
    params, ll, total_exp = fit_model(t_synthetic, T, model_name='go')

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
    params, ll, total_exp = fit_model(t_synthetic, T, model_name='mo')

    assert params is not None, "MO model should converge on failure data"
    lambda0_fit, theta_fit = params
    assert lambda0_fit > 0, f"lambda0 should be positive, got {lambda0_fit}"
    assert theta_fit > 0, f"theta should be positive, got {theta_fit}"
    assert ll is not None and ll > -np.inf


def test_fit_model_too_few_points():
    """fit_model should return None for fewer than 3 data points."""
    from modeler.models import fit_model
    t = np.array([1.0, 2.0])
    params, ll, total_exp = fit_model(t, 5.0, model_name='go')
    assert params is None, "Should return None for n < 3"


# ── Log-likelihood values vs hand computation ────────────────────────────────

def test_go_loglik_matches_hand_computation():
    from modeler.models import go_intensity
    t, T, a, b = np.array([1.0, 2.0, 4.0]), 5.0, 10.0, 0.2
    # 3*ln(a*b) - b*(1+2+4) - a*(1 - e^(-b*T)) = 3 ln 2 - 1.4 - 10(1 - e^-1)
    assert np.isclose(go_loglik([a, b], t, T), -5.6417647, atol=1e-6)
    # same thing via sum(log intensity) - mu(T)
    assert np.isclose(go_loglik([a, b], t, T),
                      np.sum(np.log(go_intensity(t, [a, b]))) - go_mu(T, [a, b]))


def test_mo_loglik_matches_hand_computation():
    from modeler.models import mo_loglik, mo_intensity
    t, T, lam0, theta = np.array([1.0, 2.0, 4.0]), 5.0, 2.0, 0.5
    # 3 ln 2 - (ln 2 + ln 3 + ln 5) - (1/0.5) ln 6
    assert np.isclose(mo_loglik([lam0, theta], t, T), -4.9052748, atol=1e-6)
    assert np.isclose(mo_loglik([lam0, theta], t, T),
                      np.sum(np.log(mo_intensity(t, [lam0, theta]))) - mo_mu(T, [lam0, theta]))


# ── Parameter recovery at production scale, for every selectable solver ──────

def _go_sample(a, b, T, seed=0):
    rng = np.random.default_rng(seed)
    n = rng.poisson(a * (1 - np.exp(-b * T)))
    u = rng.uniform(size=n)
    return np.sort(-np.log(1 - u * (1 - np.exp(-b * T))) / b)


def _mo_sample(lam0, theta, T, seed=0):
    rng = np.random.default_rng(seed)
    mu_T = np.log1p(lam0 * theta * T) / theta
    m = np.sort(rng.uniform(size=rng.poisson(mu_T))) * mu_T
    return np.expm1(theta * m) / (lam0 * theta)


@pytest.fixture(scope="module")
def solvers():
    from web.api.main import VALID_OPTIMIZATION_METHODS
    return VALID_OPTIMIZATION_METHODS


def test_go_recovers_parameters_at_250k_events(solvers):
    from modeler.models import fit_model
    a, b, T = 250000.0, 0.005, 720.0
    t = _go_sample(a, b, T)
    assert 240_000 < len(t) < 260_000
    for method in solvers:
        params, ll, total = fit_model(t, T, 'go', method=method, tol=1e-6)
        assert params is not None, method
        assert abs(params[0] / a - 1) < 0.01 and abs(params[1] / b - 1) < 0.01, (method, params)
        assert total == pytest.approx(params[0])


def test_mo_recovers_parameters_at_250k_events(solvers):
    from modeler.models import fit_model, mo_loglik
    lam0, theta, T = 2000.0, 1e-5, 720.0
    t = _mo_sample(lam0, theta, T)
    assert 240_000 < len(t) < 300_000
    lls = []
    for method in solvers:
        params, ll, _ = fit_model(t, T, 'mo', method=method, tol=1e-6)
        assert params is not None, method
        assert abs(params[0] / lam0 - 1) < 0.01 and abs(params[1] / theta - 1) < 0.01, (method, params)
        assert ll == pytest.approx(mo_loglik(params, t, T))
        lls.append(ll)
    # every solver reaches the same optimum
    assert max(lls) - min(lls) < 0.01


def test_go_fit_is_the_mle():
    """The GO fit beats any nearby parameter pair (it is not stuck at a start point)."""
    from modeler.models import fit_model
    t = _go_sample(500.0, 0.002, 720.0, seed=3)
    params, ll, _ = fit_model(t, 720.0, 'go')
    for da in (0.98, 1.02):
        for db in (0.98, 1.02):
            assert go_loglik([params[0] * da, params[1] * db], t, 720.0) < ll


# ── No valid fit ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("model", ["go", "mo"])
def test_no_fit_when_observation_period_is_zero(model):
    from modeler.models import fit_model
    assert fit_model(np.zeros(6), 0.0, model_name=model) == (None, None, None)


@pytest.mark.parametrize("model", ["go", "mo"])
def test_no_fit_for_evenly_spaced_events(model):
    """A constant failure rate has no reliability growth: the MLE is on the boundary."""
    from modeler.models import fit_model
    t = np.linspace(0, 720, 100)
    assert fit_model(t, 720.0, model_name=model) == (None, None, None)


@pytest.mark.parametrize("model", ["go", "mo"])
def test_no_fit_for_rising_failure_rate(model):
    from modeler.models import fit_model
    t = np.sort(720 * np.sqrt(np.random.default_rng(1).uniform(size=300)))
    assert fit_model(t, float(t[-1]), model_name=model) == (None, None, None)


def test_go_no_fit_when_mean_time_at_least_half_T():
    from modeler.models import fit_model
    # mean/T = 0.6 even though the data are not evenly spaced
    t = np.array([0.0, 50.0, 70.0, 80.0, 100.0])
    assert fit_model(t, 100.0, model_name='go') == (None, None, None)
