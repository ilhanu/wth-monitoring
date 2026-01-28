#!/usr/bin/env python3
"""
UMR2 Graph Generator
Generates graphs from UMR2 monitoring data.

Features:
- Temperature plot with E10 limit line (55°C)
- System status plot (heating/cooling factors, pump speed)
- Heater/Cooler state visualization
- Error markers
- Time period filtering
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
E10_TEMP_LIMIT = 55.0  # °C

# Graph colors
COLOR_SUPPLY = '#e74c3c'          # Red
COLOR_RETURN = '#3498db'          # Blue
COLOR_E10_LIMIT = '#e67e22'       # Orange
COLOR_HEATING_FACTOR = '#27ae60'  # Green
COLOR_COOLING_FACTOR = '#9b59b6'  # Purple
COLOR_PUMP = '#1abc9c'            # Teal
COLOR_HEATER = '#2ecc71'          # Light green
COLOR_COOLER = '#3498db'          # Blue
COLOR_ERROR = '#c0392b'           # Dark red

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

    # Temperature columns
    for col in ['supply_temp', 'return_temp']:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(',', '.'),
                errors='coerce'
            )

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

def create_temperature_graph(df: pd.DataFrame, save_path: str = None):
    """
    Create temperature monitoring graph.

    - Supply temperature (red line)
    - Return temperature (blue line)
    - E10 limit (orange dashed line at 55°C)
    - Heating factor (green fill)
    - Error markers (red X)
    """
    fig, ax1 = plt.subplots(figsize=(14, 7))

    # Check if we have temperature data
    has_supply = 'supply_temp' in df.columns and df['supply_temp'].notna().any()
    has_return = 'return_temp' in df.columns and df['return_temp'].notna().any()

    if not has_supply and not has_return:
        print("Warning: No temperature data available in log file.")
        plt.close()
        return

    # Temperature axis (left)
    ax1.set_xlabel('Time')
    ax1.set_ylabel('Temperature (°C)', color='black')

    # Plot temperatures
    if has_supply:
        ax1.plot(df['timestamp'], df['supply_temp'],
                 color=COLOR_SUPPLY, label='Supply temp (aanvoer)', linewidth=1.5)
    if has_return:
        ax1.plot(df['timestamp'], df['return_temp'],
                 color=COLOR_RETURN, label='Return temp (retour)', linewidth=1.5)

    # E10 limit line
    ax1.axhline(y=E10_TEMP_LIMIT, color=COLOR_E10_LIMIT,
                linestyle='--', linewidth=2, label=f'E10 limit ({E10_TEMP_LIMIT}°C)')

    # Set reasonable y-axis range for temperature
    temp_values = []
    if has_supply:
        temp_values.extend(df['supply_temp'].dropna().tolist())
    if has_return:
        temp_values.extend(df['return_temp'].dropna().tolist())

    if temp_values:
        temp_min = min(temp_values)
        temp_max = max(temp_values)
        y_min = max(0, temp_min - 5)
        y_max = max(60, temp_max + 5)
        ax1.set_ylim(y_min, y_max)

    ax1.tick_params(axis='y')

    # Heating factor axis (right)
    ax2 = ax1.twinx()
    ax2.set_ylabel('Heating Factor (%)', color=COLOR_HEATING_FACTOR)

    # Fill area for heating factor
    if 'heating_factor' in df.columns:
        ax2.fill_between(df['timestamp'], 0, df['heating_factor'],
                         alpha=0.3, color=COLOR_HEATING_FACTOR, label='Heating factor')
    ax2.set_ylim(0, 100)
    ax2.tick_params(axis='y', labelcolor=COLOR_HEATING_FACTOR)

    # Plot error markers on temperature line
    errors = get_error_points(df)
    if not errors.empty and has_supply:
        ax1.scatter(errors['timestamp'], errors['supply_temp'],
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
    plt.title(f'UMR2 Temperature Monitor (last {hours:.1f} hours)')
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
    Create system status graph with 4 subplots:
    1. Temperatures with E10 limit
    2. Heating/Cooling Factors
    3. Pump Speed
    4. Heater/Cooler Status (step plot)
    """
    fig, axes = plt.subplots(4, 1, figsize=(14, 12), sharex=True)

    # Check if we have temperature data
    has_supply = 'supply_temp' in df.columns and df['supply_temp'].notna().any()
    has_return = 'return_temp' in df.columns and df['return_temp'].notna().any()

    # Subplot 1: Temperatures
    ax1 = axes[0]
    if has_supply:
        ax1.plot(df['timestamp'], df['supply_temp'],
                 color=COLOR_SUPPLY, label='Supply temp', linewidth=1.5)
    if has_return:
        ax1.plot(df['timestamp'], df['return_temp'],
                 color=COLOR_RETURN, label='Return temp', linewidth=1.5)
    ax1.axhline(y=E10_TEMP_LIMIT, color=COLOR_E10_LIMIT,
                linestyle='--', linewidth=1.5, label=f'E10 limit ({E10_TEMP_LIMIT}°C)')
    ax1.set_ylabel('Temperature (°C)')
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)
    ax1.set_title('Temperatures (Aanvoer & Retour)')

    # Error markers on temperature plot
    errors = get_error_points(df)
    if not errors.empty and has_supply:
        ax1.scatter(errors['timestamp'], errors['supply_temp'],
                    color=COLOR_ERROR, marker='x', s=80, linewidths=2, zorder=5)

    # Subplot 2: Heating/Cooling Factors
    ax2 = axes[1]
    if 'heating_factor' in df.columns:
        ax2.plot(df['timestamp'], df['heating_factor'],
                 color=COLOR_HEATING_FACTOR, label='Heating factor', linewidth=1.5)
    if 'cooling_factor' in df.columns:
        ax2.plot(df['timestamp'], df['cooling_factor'],
                 color=COLOR_COOLING_FACTOR, label='Cooling factor', linewidth=1.5)
    ax2.set_ylabel('Factor (%)')
    ax2.set_ylim(0, 105)
    ax2.legend(loc='upper left')
    ax2.grid(True, alpha=0.3)
    ax2.set_title('Heating & Cooling Factors')

    # Subplot 3: Pump Speed
    ax3 = axes[2]
    if 'pump_speed' in df.columns:
        ax3.plot(df['timestamp'], df['pump_speed'],
                 color=COLOR_PUMP, label='Pump speed', linewidth=1.5)
    ax3.set_ylabel('Pump Speed')
    ax3.set_ylim(0, 105)
    ax3.legend(loc='upper left')
    ax3.grid(True, alpha=0.3)
    ax3.set_title('Pump Speed')

    # Subplot 4: Heater/Cooler Status
    ax4 = axes[3]
    if 'heater_binary' in df.columns:
        ax4.fill_between(df['timestamp'], 0, df['heater_binary'] * 0.9,
                         step='post', alpha=0.5, color=COLOR_HEATER, label='Heater (CV)')
        ax4.step(df['timestamp'], df['heater_binary'] * 0.9,
                 where='post', color=COLOR_HEATER, linewidth=1.5)
    if 'cooler_binary' in df.columns:
        ax4.fill_between(df['timestamp'], 1, 1 + df['cooler_binary'] * 0.9,
                         step='post', alpha=0.5, color=COLOR_COOLER, label='Cooler (KM)')
        ax4.step(df['timestamp'], 1 + df['cooler_binary'] * 0.9,
                 where='post', color=COLOR_COOLER, linewidth=1.5)
    ax4.set_ylabel('Status')
    ax4.set_ylim(-0.1, 2.1)
    ax4.set_yticks([0.45, 1.45])
    ax4.set_yticklabels(['Heater', 'Cooler'])
    ax4.legend(loc='upper left')
    ax4.grid(True, alpha=0.3)
    ax4.set_title('Heater (CV) & Cooler (KM) Status')

    # Format x-axis
    ax4.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax4.xaxis.set_major_locator(mdates.AutoDateLocator())
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

    # Supply temperature statistics
    print(f"\nSupply Temperature (Aanvoer):")
    if 'supply_temp' in df.columns:
        supply = df['supply_temp'].dropna()
        if not supply.empty:
            print(f"  Min:     {supply.min():.1f}°C")
            print(f"  Max:     {supply.max():.1f}°C")
            print(f"  Average: {supply.mean():.1f}°C")
            print(f"  Current: {supply.iloc[-1]:.1f}°C")

            # Check how often it exceeded E10 limit
            above_limit = (supply > E10_TEMP_LIMIT).sum()
            if above_limit > 0:
                print(f"  ⚠️  Exceeded {E10_TEMP_LIMIT}°C: {above_limit} times!")
        else:
            print("  No data available")
    else:
        print("  No data available")

    # Return temperature statistics
    print(f"\nReturn Temperature (Retour):")
    if 'return_temp' in df.columns:
        ret_temp = df['return_temp'].dropna()
        if not ret_temp.empty:
            print(f"  Min:     {ret_temp.min():.1f}°C")
            print(f"  Max:     {ret_temp.max():.1f}°C")
            print(f"  Average: {ret_temp.mean():.1f}°C")
            print(f"  Current: {ret_temp.iloc[-1]:.1f}°C")
        else:
            print("  No data available")
    else:
        print("  No data available")

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
        '--temp-only',
        action='store_true',
        help='Show only the temperature graph'
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
        save_path = f"umr2_temperature_{timestamp}.png" if args.save else None
        print("\nGenerating temperature graph...")
        create_temperature_graph(df, save_path)

    if not args.temp_only:
        save_path = f"umr2_status_{timestamp}.png" if args.save else None
        print("Generating system status graph...")
        create_system_status_graph(df, save_path)

    if args.save:
        print("\nGraphs saved successfully!")


if __name__ == "__main__":
    main()
