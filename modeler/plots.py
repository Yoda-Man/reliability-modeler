
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import logging
from collections import Counter

logger = logging.getLogger(__name__)

def plot_reliability_growth(t, n, curves, results, ensemble, tt, prefix):
    try:
        plt.figure(figsize=(10,6))
        plt.plot(t, np.arange(1, n+1), 'o', label=f'Observed ({n})', alpha=0.7)
        for m, curve in curves.items():
            label = results[m][3] if m in results else m
            plt.plot(tt, curve, label=label)
        
        if ensemble is not None:
            plt.plot(tt, ensemble, '--', linewidth=2.5, label='Ensemble (recommended)')
        
        plt.xlabel('Time (hours)')
        plt.ylabel('Cumulative Failures')
        plt.title('Reliability Growth – Observed vs Predicted')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        plot_path = f"{prefix}_reliability_plot.png"
        plt.savefig(plot_path, dpi=120)
        plt.close()
        logger.info(f"Saved reliability plot to {plot_path}")
        return plot_path
    except Exception as e:
        logger.error(f"Failed to plot reliability growth: {e}")
        return None


def plot_failure_intensity(tt, curves_intensity, ensemble_intensity, prefix):
    try:
        plt.figure(figsize=(10, 6))
        
        for m, curve in curves_intensity.items():
            label = m.upper() if len(m) <= 2 else m
            plt.plot(tt, curve, label=f"{label} Intensity")

        if ensemble_intensity is not None:
            plt.plot(tt, ensemble_intensity, '--', linewidth=2.5, label='Ensemble Intensity')

        plt.xlabel('Time (hours)')
        plt.ylabel('Failures per Hour (Intensity)')
        plt.title('Failure Intensity over Time (Rate of Occurrence)')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        plot_path = f"{prefix}_intensity_plot.png"
        plt.savefig(plot_path, dpi=120)
        plt.close()
        logger.info(f"Saved intensity plot to {plot_path}")
        return plot_path
    except Exception as e:
        logger.error(f"Failed to plot failure intensity: {e}")
        return None

def plot_categories(categorized_list, prefix):
    try:
        # Prepare data
        cat_counts = Counter()
        for row in categorized_list:
            cats = row[2].split(", ")
            for c in cats:
                cat_counts[c] += 1
        
        # Sort by count (descending)
        sorted_cats = cat_counts.most_common()
        cat_names = [x[0] for x in sorted_cats]
        cat_vals = [x[1] for x in sorted_cats]

        # Trend data
        cat_df = pd.DataFrame(categorized_list, columns=['Original_Timestamp', 'Time_Hours', 'Categories', 'Description'])
        
        # Get unique categories and times
        all_cats = sorted(list(set(cat_names)))
        
        stack_data = []
        labels = []
        time_grid = np.array([])
        
        if not cat_df.empty:
            max_time = cat_df['Time_Hours'].max()
            time_grid = np.linspace(0, max_time, 200)
            
            for cat in all_cats:
                # Filter events for this category
                cat_events = cat_df[cat_df['Categories'].apply(lambda x: cat in x.split(", "))]
                event_times = np.sort(cat_events['Time_Hours'].values)
                
                # Calculate cumulative counts at each time step in time_grid
                counts = np.searchsorted(event_times, time_grid, side='right')
                stack_data.append(counts)
                labels.append(cat)

            # Plotting
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
            
            # 1. Horizontal Bar Chart
            y_pos = np.arange(len(cat_names))
            ax1.barh(y_pos, cat_vals, align='center', color='skyblue')
            ax1.set_yticks(y_pos)
            ax1.set_yticklabels(cat_names)
            ax1.invert_yaxis()  # labels read top-to-bottom
            ax1.set_xlabel('Total Failures')
            ax1.set_title('Failures by Category')
            
            # Add text labels on bars
            for i, v in enumerate(cat_vals):
                ax1.text(v, i, str(v), color='black', va='center', fontweight='bold')

            # 2. Stacked Area Chart
            if stack_data:
                ax2.stackplot(time_grid, stack_data, labels=labels, alpha=0.7)
                ax2.set_xlabel('Time (hours)')
                ax2.set_ylabel('Cumulative Failures')
                ax2.set_title('Category Trends Over Time')
                ax2.legend(loc='upper left', fontsize='small')
                ax2.grid(True, alpha=0.3)

            plt.tight_layout()
            cat_plot_path = f"{prefix}_category_plot.png"
            plt.savefig(cat_plot_path, dpi=120)
            plt.close()
            logger.info(f"Saved category plot to {cat_plot_path}")
            return cat_plot_path
            
    except Exception as e:
        logger.error(f"Failed to create category plot: {e}")
        return None
