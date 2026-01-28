#!/usr/bin/env python3
"""
UMR2 Graph Generator
Generates graphs from UMR2 monitoring data.

Features:
- System status plot (heating/cooling factors, pump speed)
- Heater/Cooler state visualization
- Error markers
- Time period filtering

Note: Temperature sensors are not available on this device via API.
      E10 errors are detected via state/message fields.
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np

# =============================================================================
# Configuration
# =============================================================================

DEFAULT_LOG_FILE = "umr2_log.csv"
DEFAULT_HOURS = 24

# Graph colors
COLOR_HEATING_FACTOR = '#e74c3c'  # Red
COLOR_COOLING_FACTOR = '#3498db'  # Blue
COLOR_PUMP = '#9b59b6'            # Purple
COLOR_HEATER = '#27ae60'          # Green
COLOR_COOLER = '#1abc9c'          # Teal
COLOR_ERROR = '#c0392b'           # Dark red
COLOR_OK = '#2ecc71'              # Light green

# =============================================================================
# Data Loading and Processing
# =============================================================================

def load_data(log_file: str) -> pd.DataFrame:
    """Load CSV data into a DataFrame."""
    if not Path(log_file).exists():
        print(f"Error: Log file '{log_file}' not found.")
        print("Run umr2_monitor.py first to collect data.")
        sys.exit(1)

    df = pd.read_csv(log_file, parse_dates=['timestamp'])

    if df.empty:
        print(f"Error: Log file '{log_file}' is empty.")
        sys.exit(1)

    return df


def filter_by_hours(df: pd.DataFrame, hours: int) -> pd.DataFrame:
    """Filter DataFrame to only include data from the last N hours."""
    if hours <= 0:
        return df

    cutoff = datetime.now() - timedelta(hours=hours)
    filtered = df[df['timestamp'] >= cutoff]

    if filtered.empty:
        print(f"Warning: No data in the last {hours} hours.")
        print(f"Using all available data instead.")
        return df

    return filtered


def prepare_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Convert string columns to numeric where applicable."""
    df = df.copy()

    # Factor columns - remove % sign
    for col in ['heating_factor', 'cooling_factor']:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace('%', '').str.strip(),
                errors='coerce'
            )

    # Pump speed column
    if 'pump_speed' in df.columns:
        df['pump_speed'] = pd.to_numeric(df['pump_speed'], errors='coerce')

    # Heater state - convert to binary
    if 'heater_state' in df.columns:
        df['heater_binary'] = df['heater_state'].str.lower().isin(['aan', 'on', '1']).astype(int)

    # Cooler state - convert to binary
    if 'cooler_state' in df.columns:
        df['cooler_binary'] = df['cooler_state'].str.lower().isin(['aan', 'on', '1']).astype(int)

    # State OK/Error - convert to binary
    if 'state' in df.columns:
        df['state_ok'] = df['state'].str.upper().isin(['OK']).astype(int)

    return df


def get_error_points(df: pd.DataFrame) -> pd.DataFrame:
    """Extract rows where errors occurred."""
    if 'error' not in df.columns:
        return pd.DataFrame()

    errors = df[df['error'].notna() & (df['error'] != '')]
    return errors


# =============================================================================
# Graph Generation
# =============================================================================

def create_heating_graph(df: pd.DataFrame, save_path: str = None):
    """
    Create heating system graph.

    - Heating factor (red line)
    - Cooling factor (blue line)
    - Pump speed (purple line)
    - Error markers (red X)
    """
    fig, ax1 = plt.subplots(figsize=(14, 7))

    # Factor axis (left)
    ax1.set_xlabel('Time')
    ax1.set_ylabel('Factor (%)', color='black')

    # Plot factors
    ax1.plot(df['timestamp'], df['heating_factor'],
             color=COLOR_HEATING_FACTOR, label='Heating factor', linewidth=1.5)
    ax1.plot(df['timestamp'], df['cooling_factor'],
             color=COLOR_COOLING_FACTOR, label='Cooling factor', linewidth=1.5)

    ax1.set_ylim(0, 105)
    ax1.tick_params(axis='y')

    # Pump speed axis (right)
    ax2 = ax1.twinx()
    ax2.set_ylabel('Pump Speed', color=COLOR_PUMP)

    ax2.plot(df['timestamp'], df['pump_speed'],
             color=COLOR_PUMP, label='Pump speed', linewidth=1.5, linestyle='--')
    ax2.set_ylim(0, 105)
    ax2.tick_params(axis='y', labelcolor=COLOR_PUMP)

    # Plot error markers
    errors = get_error_points(df)
    if not errors.empty:
        # Plot errors at max factor value for visibility
        error_y = errors['heating_factor'].fillna(50)
        ax1.scatter(errors['timestamp'], error_y,
                    color=COLOR_ERROR, marker='x', s=100, linewidths=2,
                    label='Error', zorder=5)

    # Format x-axis
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax1.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.xticks(rotation=45)

    # Legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

    # Title and grid
    time_range = df['timestamp'].max() - df['timestamp'].min()
    hours = time_range.total_seconds() / 3600
    plt.title(f'UMR2 Heating/Cooling Factors (last {hours:.1f} hours)')
    ax1.grid(True, alpha=0.3)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved: {save_path}")
    else:
        plt.show()

    plt.close()


def create_system_status_graph(df: pd.DataFrame, save_path: str = None):
    """
    Create system status graph with 3 subplots:
    1. Heating/Cooling Factors
    2. Pump Speed
    3. Heater/Cooler Status (step plot)
    """
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

    # Subplot 1: Heating/Cooling Factors
    ax1 = axes[0]
    ax1.plot(df['timestamp'], df['heating_factor'],
             color=COLOR_HEATING_FACTOR, label='Heating factor', linewidth=1.5)
    ax1.plot(df['timestamp'], df['cooling_factor'],
             color=COLOR_COOLING_FACTOR, label='Cooling factor', linewidth=1.5)
    ax1.set_ylabel('Factor (%)')
    ax1.set_ylim(0, 105)
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)
    ax1.set_title('Heating & Cooling Factors')

    # Error markers on factor plot
    errors = get_error_points(df)
    if not errors.empty:
        error_y = errors['heating_factor'].fillna(50)
        ax1.scatter(errors['timestamp'], error_y,
                    color=COLOR_ERROR, marker='x', s=80, linewidths=2, zorder=5)

    # Subplot 2: Pump Speed
    ax2 = axes[1]
    ax2.plot(df['timestamp'], df['pump_speed'],
             color=COLOR_PUMP, label='Pump speed', linewidth=1.5)
    ax2.set_ylabel('Pump Speed')
    ax2.set_ylim(0, 105)
    ax2.legend(loc='upper left')
    ax2.grid(True, alpha=0.3)
    ax2.set_title('Pump Speed')

    # Subplot 3: Heater/Cooler Status
    ax3 = axes[2]
    if 'heater_binary' in df.columns:
        ax3.fill_between(df['timestamp'], 0, df['heater_binary'] * 0.9,
                         step='post', alpha=0.5, color=COLOR_HEATER, label='Heater (CV)')
        ax3.step(df['timestamp'], df['heater_binary'] * 0.9,
                 where='post', color=COLOR_HEATER, linewidth=1.5)
    if 'cooler_binary' in df.columns:
        ax3.fill_between(df['timestamp'], 1, 1 + df['cooler_binary'] * 0.9,
                         step='post', alpha=0.5, color=COLOR_COOLER, label='Cooler (KM)')
        ax3.step(df['timestamp'], 1 + df['cooler_binary'] * 0.9,
                 where='post', color=COLOR_COOLER, linewidth=1.5)
    ax3.set_ylabel('Status')
    ax3.set_ylim(-0.1, 2.1)
    ax3.set_yticks([0.45, 1.45])
    ax3.set_yticklabels(['Heater', 'Cooler'])
    ax3.legend(loc='upper left')
    ax3.grid(True, alpha=0.3)
    ax3.set_title('Heater (CV) & Cooler (KM) Status')

    # Format x-axis
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax3.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.xticks(rotation=45)

    # Overall title
    time_range = df['timestamp'].max() - df['timestamp'].min()
    hours = time_range.total_seconds() / 3600
    fig.suptitle(f'UMR2 System Status (last {hours:.1f} hours)', fontsize=14, fontweight='bold')

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved: {save_path}")
    else:
        plt.show()

    plt.close()


# =============================================================================
# Summary Statistics
# =============================================================================

def print_summary(df: pd.DataFrame):
    """Print a text summary of the data."""
    print()
    print("=" * 60)
    print("UMR2 Data Summary")
    print("=" * 60)

    # Time range
    start_time = df['timestamp'].min()
    end_time = df['timestamp'].max()
    duration = end_time - start_time

    print(f"\nTime Period:")
    print(f"  Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  End:   {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Duration: {duration}")
    print(f"  Data points: {len(df)}")

    # State statistics
    print(f"\nSystem State:")
    if 'state' in df.columns:
        state_counts = df['state'].value_counts()
        for state, count in state_counts.items():
            pct = count / len(df) * 100
            print(f"  {state}: {count} ({pct:.1f}%)")

    # Heating factor
    print(f"\nHeating Factor:")
    if 'heating_factor' in df.columns:
        factor = df['heating_factor'].dropna()
        if not factor.empty:
            print(f"  Min:     {factor.min():.0f}%")
            print(f"  Max:     {factor.max():.0f}%")
            print(f"  Average: {factor.mean():.1f}%")
            print(f"  Current: {factor.iloc[-1]:.0f}%")
        else:
            print("  No data available")

    # Cooling factor
    print(f"\nCooling Factor:")
    if 'cooling_factor' in df.columns:
        factor = df['cooling_factor'].dropna()
        if not factor.empty:
            print(f"  Min:     {factor.min():.0f}%")
            print(f"  Max:     {factor.max():.0f}%")
            print(f"  Average: {factor.mean():.1f}%")
            print(f"  Current: {factor.iloc[-1]:.0f}%")
        else:
            print("  No data available")

    # Pump speed
    print(f"\nPump Speed:")
    if 'pump_speed' in df.columns:
        pump = df['pump_speed'].dropna()
        if not pump.empty:
            print(f"  Min:     {pump.min():.0f}")
            print(f"  Max:     {pump.max():.0f}")
            print(f"  Average: {pump.mean():.1f}")
            print(f"  Current: {pump.iloc[-1]:.0f}")
        else:
            print("  No data available")

    # Heater status
    if 'heater_binary' in df.columns:
        heater = df['heater_binary'].dropna()
        if not heater.empty:
            heater_on_pct = heater.mean() * 100
            print(f"\nHeater (CV):")
            print(f"  On:      {heater_on_pct:.1f}% of the time")
            print(f"  Current: {'On' if heater.iloc[-1] == 1 else 'Off'}")

    # Cooler status
    if 'cooler_binary' in df.columns:
        cooler = df['cooler_binary'].dropna()
        if not cooler.empty:
            cooler_on_pct = cooler.mean() * 100
            print(f"\nCooler (KM):")
            print(f"  On:      {cooler_on_pct:.1f}% of the time")
            print(f"  Current: {'On' if cooler.iloc[-1] == 1 else 'Off'}")

    # Mode statistics
    print(f"\nOperating Mode:")
    if 'mode' in df.columns:
        mode_counts = df['mode'].value_counts()
        for mode, count in mode_counts.items():
            pct = count / len(df) * 100
            print(f"  {mode}: {count} ({pct:.1f}%)")

    # Errors
    errors = get_error_points(df)
    print(f"\nErrors:")
    print(f"  Total error events: {len(errors)}")
    if not errors.empty:
        print(f"  Error types detected:")
        error_types = errors['error'].value_counts()
        for error_type, count in error_types.items():
            print(f"    - {error_type}: {count} times")

    # Connection errors
    connection_errors = df[df['error'] == 'CONNECTION_ERROR']
    if not connection_errors.empty:
        print(f"\n  Connection errors: {len(connection_errors)}")

    print()
    print("=" * 60)


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="UMR2 Graph Generator - Visualize your heating system data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python umr2_graphs.py                    Show graphs for last 24 hours
  python umr2_graphs.py --hours 48         Show last 48 hours
  python umr2_graphs.py --hours 168        Show last week
  python umr2_graphs.py --save             Save as PNG instead of showing
  python umr2_graphs.py --summary          Text summary only (no graphs)
  python umr2_graphs.py --hours 0          Show all data (no time filter)

Note:
  Temperature sensors are not available on this device via API.
  E10 errors are detected via state/message fields and shown as markers.
        """
    )

    parser.add_argument(
        '--hours',
        type=int,
        default=DEFAULT_HOURS,
        help=f'Show data from the last N hours (default: {DEFAULT_HOURS}, 0 for all data)'
    )

    parser.add_argument(
        '--file', '-f',
        type=str,
        default=DEFAULT_LOG_FILE,
        help=f'CSV log file to read (default: {DEFAULT_LOG_FILE})'
    )

    parser.add_argument(
        '--save', '-s',
        action='store_true',
        help='Save graphs as PNG files instead of displaying'
    )

    parser.add_argument(
        '--summary',
        action='store_true',
        help='Print text summary only (no graphs)'
    )

    parser.add_argument(
        '--heating-only',
        action='store_true',
        help='Show only the heating/cooling factors graph'
    )

    parser.add_argument(
        '--status-only',
        action='store_true',
        help='Show only the system status graph'
    )

    args = parser.parse_args()

    # Load and prepare data
    print(f"Loading data from {args.file}...")
    df = load_data(args.file)
    df = filter_by_hours(df, args.hours)
    df = prepare_numeric_columns(df)

    print(f"Loaded {len(df)} data points")

    # Print summary
    if args.summary:
        print_summary(df)
        return

    # Always print summary first
    print_summary(df)

    # Generate graphs
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    if not args.status_only:
        save_path = f"umr2_heating_{timestamp}.png" if args.save else None
        print("\nGenerating heating/cooling graph...")
        create_heating_graph(df, save_path)

    if not args.heating_only:
        save_path = f"umr2_status_{timestamp}.png" if args.save else None
        print("Generating system status graph...")
        create_system_status_graph(df, save_path)

    if args.save:
        print("\nGraphs saved successfully!")


if __name__ == "__main__":
    main()
