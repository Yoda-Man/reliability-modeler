
import numpy as np
from scipy.optimize import minimize, minimize_scalar
import logging

logger = logging.getLogger(__name__)

def go_loglik(params, t, T):
    a, b = params
    if a <= 0 or b <= 0: return -np.inf
    n = len(t)
    return n * np.log(a * b) - b * np.sum(t) - a * (1 - np.exp(-b * T))


def go_mu(t, params):
    a, b = params
    return a * (1 - np.exp(-b * t))


def go_intensity(t, params):
    """Calculates failure intensity (rate) for GO model: lambda(t) = a * b * exp(-b*t)"""
    a, b = params
    return a * b * np.exp(-b * t)


def mo_loglik(params, t, T):
    lambda0, theta = params
    if lambda0 <= 0 or theta <= 0: return -np.inf
    n = len(t)
    return n * np.log(lambda0) - np.sum(np.log(1 + lambda0 * theta * t)) - (1 / theta) * np.log(1 + lambda0 * theta * T)


def mo_mu(t, params):
    lambda0, theta = params
    return (1 / theta) * np.log(1 + lambda0 * theta * t)


def mo_intensity(t, params):
    """Calculates failure intensity (rate) for MO model: lambda(t) = lambda0 / (1 + lambda0 * theta * t)"""
    lambda0, theta = params
    return lambda0 / (1 + lambda0 * theta * t)


# Search ranges for the profiled shape parameter, expressed as multiples of 1/T
# (b for GO, beta = lambda0*theta for MO). Both are searched in log space.
_SHAPE_RANGE = (1e-6, 1e6)
# A fit whose optimum lies within this fraction of the (log-space) search range
# of a bound is a boundary solution, i.e. there is no finite interior MLE.
_BOUNDARY_FRACTION = 0.01


def _near_bound(x, lo, hi):
    margin = _BOUNDARY_FRACTION * (hi - lo)
    return x <= lo + margin or x >= hi - margin


def go_profile_negloglik(log_b, t, T):
    """Negative GO log-likelihood (per event) with ``a`` profiled out.

    For fixed b the MLE of a is n / (1 - exp(-b*T)), which turns the 2-D
    problem into a 1-D one over log(b).
    """
    n = len(t)
    b = np.exp(log_b)
    a = n / -np.expm1(-b * T)
    return -go_loglik([a, b], t, T) / n


def mo_profile_negloglik(log_beta, t, T):
    """Negative MO log-likelihood (per event) with theta profiled out.

    Writing beta = lambda0*theta, the MLE of theta for fixed beta is
    log(1 + beta*T) / n, so only log(beta) has to be searched.
    """
    n = len(t)
    beta = np.exp(log_beta)
    theta = np.log1p(beta * T) / n
    return -mo_loglik([beta / theta, theta], t, T) / n


def fit_model(t, T, model_name='go', method='L-BFGS-B', tol=1e-10, maxiter=5000):
    """Maximum-likelihood fit of the GO or MO NHPP model.

    Returns ``(params, loglik, total_expected)``, or ``(None, None, None)``
    when no valid fit exists: fewer than 3 events, ``T <= 0``, a mean event
    time of at least T/2 (no reliability growth), or an optimum that lies on the boundary of the search
    range (no reliability growth / degenerate data).

    GO is solved exactly: ``a`` is profiled out analytically and log(b) is
    found with a bounded 1-D search, so ``method``/``tol`` do not apply.
    MO profiles out theta analytically and searches log(lambda0*theta) with
    the chosen scipy ``method`` and ``tol``.
    """
    t = np.asarray(t, dtype=float)
    n = len(t)
    none = (None, None, None)
    if n < 3:
        logger.warning("Not enough data points to fit model (n < 3).")
        return none
    if not np.isfinite(T) or T <= 0:
        logger.warning("Cannot fit %s model: observation period T=%s is not positive.", model_name, T)
        return none

    # Both models have a decreasing intensity. When the mean event time is at
    # least T/2 the data show no reliability growth: the GO likelihood has no
    # finite maximum and the MO optimum collapses onto the constant-rate
    # boundary (the profile likelihood's slope at beta=0 is n*(T/2 - mean t)).
    if np.mean(t) / T >= 0.5:
        logger.warning("No valid %s fit: failure rate is not decreasing (mean t / T >= 0.5).", model_name)
        return none

    lo, hi = np.log(_SHAPE_RANGE[0] / T), np.log(_SHAPE_RANGE[1] / T)
    if model_name == 'go':
        res = minimize_scalar(go_profile_negloglik, bounds=(lo, hi), args=(t, T),
                              method='bounded', options={'xatol': 1e-10, 'maxiter': maxiter})
        x = float(res.x)
        b = np.exp(x)
        params = np.array([n / -np.expm1(-b * T), b])
        loglik_func = go_loglik
    else:
        # TNC names its iteration cap 'maxfun'; the other supported solvers use 'maxiter'.
        options = {'maxfun': maxiter} if method == 'TNC' else {'maxiter': maxiter}
        best = None
        for x0 in np.log(np.array([1e-3, 1e-1, 1e1, 1e3]) / T):
            res = minimize(lambda x: mo_profile_negloglik(x[0], t, T), [x0], bounds=[(lo, hi)],
                           method=method, tol=tol, options=options)
            if np.isfinite(res.fun) and (best is None or res.fun < best.fun):
                best = res
        if best is None:
            logger.warning("Failed to fit mo model.")
            return none
        x = float(best.x[0])
        beta = np.exp(x)
        theta = np.log1p(beta * T) / n
        params = np.array([beta / theta, theta])
        loglik_func = mo_loglik

    ll = loglik_func(params, t, T)
    if not np.all(np.isfinite(params)) or not np.isfinite(ll) or _near_bound(x, lo, hi):
        logger.warning("No valid %s fit: optimum is on the boundary of the parameter space.", model_name)
        return none

    if model_name == 'go':
        total_expected = params[0]
    else:
        # Use a large time to approximate asymptotic total. For MO model,
        # mu(inf) = (1/theta) * ln(1 + lambda0 * theta * inf) is unbounded,
        # so we use a practical horizon of 1e6 hours (~114 years).
        total_expected = mo_mu(1e6, params)

    return params, float(ll), float(total_expected)
