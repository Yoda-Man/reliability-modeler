
"""
SOFTWARE RELIABILITY GROWTH MODELER
Entry Point
"""

import argparse
import numpy as np
import logging
import sys
from datetime import datetime
from pathlib import Path
import matplotlib.pyplot as plt

# Import modules
from modeler.data import load_failure_data
from modeler.models import fit_model, go_mu, mo_mu
from modeler.export import export_and_summarize

def setup_logging(silent=False, output_dir=None):
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    handlers = []
    
    if not silent:
        handlers.append(logging.StreamHandler(sys.stdout))
        
    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = Path(output_dir) / f"run_{timestamp}.log"
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(level=logging.INFO, format=log_format, handlers=handlers)

def main():
    parser = argparse.ArgumentParser(description="Reliability Growth Modeler v1.0.0")
    parser.add_argument('--csv', default='input/error_log.csv')
    parser.add_argument('--config', default='fault_categories.conf')
    parser.add_argument('--model', choices=['go','mo','both'], default='both')
    parser.add_argument('--start-time', default=None)
    parser.add_argument('--multi-label', action='store_true')
    parser.add_argument('--silent', action='store_true')
    parser.add_argument('--export-only', action='store_true')
    parser.add_argument('--prefix', default=None)
    parser.add_argument('--output-dir', default='output', help="Directory to save output files")

    args = parser.parse_args()

    # Setup Directory
    # Create Year/Month/Day structure
    now = datetime.now()
    date_path = now.strftime("%Y/%m/%d")  # e.g., 2026/02/17
    
    # Base output dir from args, then append date structure
    base_output_dir = Path(args.output_dir)
    output_dir = base_output_dir / date_path
    output_dir.mkdir(parents=True, exist_ok=True)

    # Setup Logging
    silent = args.silent or args.export_only
    setup_logging(silent, output_dir=output_dir)
    logger = logging.getLogger("main")

    if not silent:
        print("Reliability Modeler v1.0.0")

    try:
        t, categorized, t0, fault_categories = load_failure_data(
            Path(args.csv), Path(args.config), args.start_time,
            multi_label=args.multi_label
        )
    except Exception as e:
        logger.critical(f"Data loading failed: {e}")
        return

    t = np.sort(t)
    T = float(t[-1]) if len(t) > 0 else 0.0
    n = len(t)

    logger.info(f"{n} failures | T = {T:.2f} hours (since {t0})")

    models_to_fit = []
    if args.model in ['go', 'both']: models_to_fit.append('go')
    if args.model in ['mo', 'both']: models_to_fit.append('mo')

    results = {}
    curves = {}
    tt = np.linspace(0, T * 1.6, 400)

    for m in models_to_fit:
        logger.info(f"Fitting model: {m}")
        params, ll, se, total_exp = fit_model(t, T, m)
        if params is not None:
            name = "Goel-Okumoto" if m == 'go' else "Musa-Okumoto"
            aic = 4 - 2*ll
            logger.info(f"{name}: AIC = {aic:.2f}")
            results[m] = (params, ll, se, total_exp)
            curves[m] = go_mu(tt, params) if m == 'go' else mo_mu(tt, params)

    ensemble = None
    if len(curves) == 2:
        ensemble = (curves['go'] + curves['mo']) / 2

    # Output Prefix
    prefix = args.prefix or datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = str(output_dir / prefix)

    # Export
    export_and_summarize(results, tt, curves, t, np.arange(1,n+1), ensemble,
                         categorized, prefix, fault_categories, t, T)
    
    logger.info("Analysis complete.")

if __name__ == "__main__":
    main()