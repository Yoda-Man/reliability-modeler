
import pandas as pd
import numpy as np
from datetime import datetime
from collections import Counter
import logging
from .plots import plot_reliability_growth, plot_categories, plot_failure_intensity
from .models import go_intensity, mo_intensity

logger = logging.getLogger(__name__)

def export_and_summarize(results, tt, curves, observed_times, observed_cum, ensemble,
                         categorized_list, prefix, fault_categories, t, T):
    if not prefix:
        prefix = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Parameters
    param_rows = []
    total_expected_dict = {}
    for m, (params, ll, se, total_exp) in results.items():
        name = "Goel-Okumoto" if m == 'go' else "Musa-Okumoto"
        param_rows.append({
            'Model': name, 'Param1': params[0], 'Param2': params[1] if len(params)>1 else np.nan,
            'Param1_SE': se[0] if len(se)>0 else np.nan, 'Param2_SE': se[1] if len(se)>1 else np.nan,
            'LogLikelihood': ll, 'AIC': 4 - 2*ll if ll is not None else np.nan
        })
        total_expected_dict[m] = total_exp
    pd.DataFrame(param_rows).to_csv(f"{prefix}_parameters.csv", index=False)

    # Predictions & Intensity
    pred_rows = []
    curves_intensity = {}
    ensemble_intensity = None

    for m, curve in curves.items():
        # Calculate intensity curve
        params = results[m][0]
        if m == 'go':
            intensity = go_intensity(tt, params)
        else:
            intensity = mo_intensity(tt, params)
        curves_intensity[m] = intensity

        for ti, mui, lami in zip(tt, curve, intensity):
            pred_rows.append({'Model': results[m][3] if m in results else m,
                              'Time_hours': round(ti,4), 'Predicted_Mean': round(mui,4),
                              'Predicted_Intensity': round(lami, 6),
                              'CI_Lower_95pct': round(mui - 1.96 * np.sqrt(max(0.1, mui)), 4),
                              'CI_Upper_95pct': round(mui + 1.96 * np.sqrt(max(0.1, mui)), 4)})
    if ensemble is not None:
        # Ensemble intensity = average of intensities
        intensities = list(curves_intensity.values())
        if len(intensities) == 2:
            ensemble_intensity = (intensities[0] + intensities[1]) / 2
            
            for ti, mui, lami in zip(tt, ensemble, ensemble_intensity):
                pred_rows.append({'Model':'Ensemble', 'Time_hours':round(ti,4), 'Predicted_Mean':round(mui,4),
                                  'Predicted_Intensity': round(lami, 6),
                                  'CI_Lower_95pct':np.nan, 'CI_Upper_95pct':np.nan})
    for ti, ci in zip(observed_times, observed_cum):
        pred_rows.append({'Model':'Observed', 'Time_hours':round(ti,4), 'Predicted_Mean':ci,
                          'Predicted_Intensity': np.nan,
                          'CI_Lower_95pct':np.nan, 'CI_Upper_95pct':np.nan})
    pd.DataFrame(pred_rows).to_csv(f"{prefix}_predictions.csv", index=False)

    # Categorized
    cat_df = pd.DataFrame(categorized_list, columns=['Original_Timestamp', 'Time_Hours', 'Categories', 'Description'])
    cat_df.to_csv(f"{prefix}_categorized.csv", index=False)

    # Category trends
    cat_df['Time_Hours_Rounded'] = cat_df['Time_Hours'].round(0)
    grouped = cat_df.groupby(['Categories', 'Time_Hours_Rounded']).size().unstack(fill_value=0).cumsum(axis=1)
    trend_df = grouped.reset_index().melt(id_vars=['Categories'], var_name='Time_Hours', value_name='Cumulative_Failures')
    trend_df.to_csv(f"{prefix}_category_trends.csv", index=False)

    # Human-friendly summary
    current_failures = len(t)
    current_time = T

    summary_lines = []
    summary_lines.append("=== Easy-to-Understand Reliability Summary ===\n")
    summary_lines.append(f"We have seen {current_failures} failures so far after {current_time:.1f} hours of testing/runtime.\n")

    if ensemble is not None:
        ens_at_500  = np.interp(500,  tt, ensemble)
        ens_at_2000 = np.interp(2000, tt, ensemble)
        ens_at_5000 = np.interp(5000, tt, ensemble)
        more_500  = max(0, round(ens_at_500  - current_failures))
        more_2000 = max(0, round(ens_at_2000 - current_failures))
        more_5000 = max(0, round(ens_at_5000 - current_failures))

        summary_lines.append("Best guess (average of two models):")
        summary_lines.append(f"  * In the next ~{500 - current_time:.0f} hours -> about {more_500} more failures expected")
        summary_lines.append(f"  * In the next ~{2000 - current_time:.0f} hours -> about {more_2000} more failures expected")
        summary_lines.append(f"  * Long-term (after ~{5000 - current_time:.0f} more hours) -> total around {round(ens_at_5000)} failures expected\n")

    if results:
        best_model = min(results, key=lambda k: 4 - 2*results[k][1])  # lowest AIC
        best_total = total_expected_dict[best_model]
        cat_counts = Counter()
        for row in categorized_list:
            cats = row[2].split(", ")
            for c in cats:
                cat_counts[c] += 1
        total_seen = sum(cat_counts.values())

        if total_seen > 0:
            summary_lines.append("Biggest problem areas (rough estimate):")
            for cat, count in cat_counts.most_common(5):
                proportion = count / total_seen
                remaining = round(proportion * max(0, best_total - current_failures))
                summary_lines.append(f"  * {cat}: {count} so far -> roughly {remaining} more to find")
            summary_lines.append("")

    with open(f"{prefix}_human_summary.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines))
    
    logger.info(f"Saved summary to {prefix}_human_summary.txt")

    # Generate Plots
    plot_path = plot_reliability_growth(t, len(t), curves, results, ensemble, tt, prefix)
    cat_plot_path = plot_categories(categorized_list, prefix)
    intensity_plot_path = plot_failure_intensity(tt, curves_intensity, ensemble_intensity, prefix)

    print("\n".join(summary_lines))
    print(f"\nSaved files with prefix: {prefix}")
    print(f"  * {prefix}_human_summary.txt     <- plain English explanation")
    print(f"  * {prefix}_category_trends.csv   <- cumulative failures per category over time")
    print(f"  * {prefix}_reliability_plot.png  <- reliability growth chart")
    print(f"  * {prefix}_intensity_plot.png    <- failure intensity (stability) chart")
    print(f"  * {prefix}_category_plot.png     <- Visual breakdown by category")
    print("  * parameters.csv / predictions.csv / categorized.csv")
