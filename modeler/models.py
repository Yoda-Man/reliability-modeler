
import numpy as np
from scipy.optimize import minimize
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


def numerical_hessian(fun, x, args=(), eps=1e-5):
    n = len(x)
    H = np.zeros((n, n))
    f0 = fun(x, *args)
    for i in range(n):
        x1 = x.copy(); x1[i] += eps
        x2 = x.copy(); x2[i] -= eps
        f1 = fun(x1, *args)
        f2 = fun(x2, *args)
        H[i,i] = (f1 - 2*f0 + f2) / (eps**2)
        for j in range(i+1, n):
            x11 = x.copy(); x11[i] += eps; x11[j] += eps
            x12 = x.copy(); x12[i] += eps; x12[j] -= eps
            x21 = x.copy(); x21[i] -= eps; x21[j] += eps
            x22 = x.copy(); x22[i] -= eps; x22[j] -= eps
            f11 = fun(x11, *args)
            f12 = fun(x12, *args)
            f21 = fun(x21, *args)
            f22 = fun(x22, *args)
            H[i,j] = H[j,i] = (f11 - f12 - f21 + f22) / (4 * eps**2)
    return H


def fit_model(t, T, model_name='go', method='L-BFGS-B', tol=1e-10):
    n = len(t)
    if n < 3:
        logger.warning("Not enough data points to fit model (n < 3).")
        return None, None, None, None

    if model_name == 'go':
        loglik_func = go_loglik
        initials = [[n*1.2, 0.05], [n*1.5, 0.03], [n*2.0, 0.08], [n*1.1, 0.2], [n*3.0, 0.1]]
        bounds = [(max(1, n*0.5), None), (1e-6, None)]
        mu_func = go_mu
    else:
        loglik_func = mo_loglik
        lambda0_guess = n / T * np.array([0.5, 1.0, 2.0, 3.0]) if T > 0 else np.array([10,50,100])
        theta_guess = np.array([0.005, 0.01, 0.05, 0.1, 0.2])
        initials = [[l0, th] for l0 in lambda0_guess for th in theta_guess]
        bounds = [(1e-6,None), (1e-6,None)]
        mu_func = mo_mu

    best_ll, best_params = -np.inf, None
    for x0 in initials:
        res = minimize(lambda p: -loglik_func(p, t, T), x0, bounds=bounds,
                       method=method, tol=tol)
        if res.success:
            ll = loglik_func(res.x, t, T)
            if ll > best_ll:
                best_ll = ll
                best_params = res.x

    if best_params is None:
        logger.warning(f"Failed to fit {model_name} model.")
        return None, None, None, None

    try:
        neg_ll = lambda p: -loglik_func(p, t, T)
        H = numerical_hessian(neg_ll, best_params, args=(t, T))
        cov = np.linalg.inv(H)
        se = np.sqrt(np.diag(cov))
    except Exception as e:
        logger.debug(f"Hessian calculation failed for {model_name}: {e}")
        se = np.full(len(best_params), np.nan)

    if model_name == 'go':
        total_expected = best_params[0]
    else:
        total_expected = mo_mu(1e9, best_params)  # large-t approximation

    return best_params, best_ll, se, total_expected
