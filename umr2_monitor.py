#!/usr/bin/env python3
"""
UMR2 Pro Monitoring System
Monitors a WTH UMR2 Pro underfloor heating controller via its JSON API.

Features:
- Polls status every 60 seconds via JSON API
- Logs all data to CSV including temperatures
- Alerts on errors (E10 when supply temp >55C, etc.)
- Optional Telegram notifications
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime
from typing import Optional

import requests

# =============================================================================
# Configuration
# =============================================================================

UMR_IP = "192.168.1.185"
POLL_INTERVAL = 60  # seconds
LOG_FILE = "umr2_log.csv"
ERROR_LOG_FILE = "umr2_errors.log"
REQUEST_TIMEOUT = 10  # seconds

# E10 temperature limit
E10_TEMP_LIMIT = 55.0  # °C - supply temp above this triggers E10

# Optional Telegram notifications
TELEGRAM_ENABLED = False
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""

# Error codes to detect in message field
ERROR_CODES = ["E10", "E11", "E21", "E22", "E30", "E90"]

# =============================================================================
# ANSI Color Codes
# =============================================================================

class Colors:
    """ANSI escape codes for terminal colors."""
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

# =============================================================================
# CSV Field Order
# =============================================================================

CSV_FIELDS = [
    'timestamp',
    'supply_temp',     # aanvoertemperatuur (inputs.max.temperature)
    'return_temp',     # retourtemperatuur (inputs.return.temperature)
    'state',           # main.state - "OK" or error
    'message',         # main.message - "OK" or error code like "E10"
    'mode',            # heating/cooling/off
    'heating_factor',  # 0-100%
    'cooling_factor',  # 0-100%
    'pump_speed',      # pump speed
    'heater_state',    # on/off
    'cooler_state',    # on/off
    'error',           # detected errors
]

# =============================================================================
# Monitoring State
# =============================================================================

class MonitorState:
    """Tracks monitoring state across polls."""

    def __init__(self):
        self.poll_count = 0
        self.error_count = 0
        self.last_error: Optional[str] = None
        self.last_error_time: Optional[datetime] = None
        self.consecutive_failures = 0


# =============================================================================
# Core Functions
# =============================================================================

def fetch_json(endpoint: str) -> Optional[dict]:
    """Fetch JSON data from UMR2 API endpoint."""
    url = f"http://{UMR_IP}/{endpoint}"
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None
    except ValueError:  # JSON decode error
        return None


def fetch_status() -> Optional[dict]:
    """Fetch status data from UMR2 API."""
    # Fetch main status
    main_data = fetch_json("get.json?f=$.status.main.*")
    if main_data is None:
        return None

    # Fetch outputs status
    outputs_data = fetch_json("get.json?f=$.status.outputs.*")
    if outputs_data is None:
        return None

    # Fetch supply temperature (aanvoertemperatuur) - inputs.max
    supply_data = fetch_json("get.json?f=$.status.inputs.max.*")

    # Fetch return temperature - inputs.return
    return_data = fetch_json("get.json?f=$.status.inputs.return.*")

    return {
        'main': main_data.get('status', {}).get('main', {}),
        'outputs': outputs_data.get('status', {}).get('outputs', {}),
        'supply': supply_data.get('status', {}).get('inputs', {}).get('max', {}) if supply_data else {},
        'return': return_data.get('status', {}).get('inputs', {}).get('return', {}) if return_data else {},
    }


def parse_temperature(value) -> Optional[float]:
    """Parse temperature value, handling various formats."""
    if value is None or value == '':
        return None
    try:
        # Handle string with comma as decimal separator
        if isinstance(value, str):
            value = value.replace(',', '.')
        return float(value)
    except (ValueError, TypeError):
        return None


def parse_status_data(raw_data: dict) -> dict:
    """Parse raw API data into our normalized format."""
    main = raw_data.get('main', {})
    outputs = raw_data.get('outputs', {})
    supply = raw_data.get('supply', {})
    return_data = raw_data.get('return', {})

    # Mode translation
    mode_map = {
        'heating': 'verwarmen',
        'cooling': 'koelen',
        'off': 'uit',
        'on': 'aan',
    }

    mode = main.get('mode', '')
    mode_display = mode_map.get(mode, mode)

    heater_state = outputs.get('heater', {}).get('state', '')
    heater_display = mode_map.get(heater_state, heater_state)

    cooler_state = outputs.get('cooler', {}).get('state', '')
    cooler_display = mode_map.get(cooler_state, cooler_state)

    # Parse temperatures
    supply_temp = parse_temperature(supply.get('temperature'))
    return_temp = parse_temperature(return_data.get('temperature'))

    data = {
        'supply_temp': supply_temp,
        'return_temp': return_temp,
        'state': main.get('state', ''),
        'message': main.get('message', ''),
        'mode': mode_display,
        'heating_factor': f"{main.get('heatFactor', 0)}%",
        'cooling_factor': f"{main.get('coolFactor', 0)}%",
        'pump_speed': outputs.get('pump', {}).get('speed', 0),
        'heater_state': heater_display,
        'cooler_state': cooler_display,
    }

    return data


def detect_errors(data: dict) -> list:
    """Detect error conditions from parsed data."""
    errors = []

    # Check supply temperature for E10 condition
    supply_temp = data.get('supply_temp')
    if supply_temp is not None and supply_temp > E10_TEMP_LIMIT:
        errors.append(f"E10(temp:{supply_temp:.1f}C)")

    # Check main state
    state = str(data.get('state', '')).upper()
    if state and state != 'OK':
        errors.append(f"STATE:{state}")

    # Check message for error codes
    message = str(data.get('message', '')).upper()
    if message and message != 'OK':
        # Check for known error codes
        for code in ERROR_CODES:
            if code in message:
                # Don't duplicate E10 if we already detected it from temperature
                if code == 'E10' and any('E10' in e for e in errors):
                    continue
                errors.append(code)
                break
        else:
            # Unknown error in message
            if message not in ['', 'OK']:
                errors.append(f"MSG:{message}")

    return errors


def log_to_csv(data: dict, log_file: str):
    """Append data to CSV log file."""
    file_exists = os.path.exists(log_file)

    with open(log_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction='ignore')

        if not file_exists:
            writer.writeheader()

        writer.writerow(data)


def log_error(error_msg: str, error_log_file: str):
    """Append error to error log file."""
    timestamp = datetime.now().isoformat()
    with open(error_log_file, 'a', encoding='utf-8') as f:
        f.write(f"{timestamp} | {error_msg}\n")


def send_telegram_notification(message: str) -> bool:
    """Send Telegram notification. Returns True if successful."""
    if not TELEGRAM_ENABLED or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except requests.RequestException:
        return False


def format_temp(temp: Optional[float]) -> str:
    """Format temperature for display."""
    if temp is None:
        return "?"
    return f"{temp:.1f}C"


def format_status_line(data: dict, state: MonitorState, has_error: bool, errors: list) -> str:
    """Format a compact status line for console output."""
    timestamp = datetime.now().strftime("%H:%M:%S")

    supply_temp = format_temp(data.get('supply_temp'))
    return_temp = format_temp(data.get('return_temp'))
    mode = data.get('mode', '?')
    heat_factor = data.get('heating_factor', '?')
    pump = data.get('pump_speed', '?')
    heater = data.get('heater_state', '?')

    if has_error:
        status_icon = f"{Colors.RED}ERROR{Colors.RESET}"
        error_str = ', '.join(errors)
        line = f"[{timestamp}] {status_icon} | Supply: {supply_temp} | Return: {return_temp} | Mode: {mode} | Heat: {heat_factor} | Pump: {pump} | CV: {heater} | Polls: {state.poll_count}"
        line += f"\n  {Colors.YELLOW}ALERT:{Colors.RESET} {error_str}"
    else:
        status_icon = f"{Colors.GREEN}OK{Colors.RESET}"
        line = f"[{timestamp}] {status_icon} | Supply: {supply_temp} | Return: {return_temp} | Mode: {mode} | Heat: {heat_factor} | Pump: {pump} | CV: {heater} | Polls: {state.poll_count}"

    return line


def format_connection_error_line(state: MonitorState) -> str:
    """Format a connection error status line."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    return f"[{timestamp}] {Colors.YELLOW}CONNECTION_ERROR{Colors.RESET} | Failed to reach UMR2 at {UMR_IP} | Polls: {state.poll_count} | Consecutive failures: {state.consecutive_failures}"


def poll_once(state: MonitorState) -> dict:
    """Perform a single poll of the UMR2."""
    state.poll_count += 1

    # Fetch status data
    raw_data = fetch_status()

    if raw_data is None:
        state.consecutive_failures += 1
        print(format_connection_error_line(state))

        error_data = {
            'timestamp': datetime.now().isoformat(),
            'error': 'CONNECTION_ERROR',
        }
        for field in CSV_FIELDS:
            if field not in error_data:
                error_data[field] = ''

        log_to_csv(error_data, LOG_FILE)
        return error_data

    state.consecutive_failures = 0

    # Parse data
    data = parse_status_data(raw_data)
    data['timestamp'] = datetime.now().isoformat()

    # Detect errors
    errors = detect_errors(data)
    has_error = len(errors) > 0

    if has_error:
        error_str = ', '.join(errors)
        data['error'] = error_str
        state.error_count += 1

        log_error(f"Errors: {error_str}", ERROR_LOG_FILE)

        # Send Telegram notification for NEW errors only
        if state.last_error != error_str:
            state.last_error = error_str
            state.last_error_time = datetime.now()

            supply_temp = data.get('supply_temp')
            temp_info = f"Supply temp: {supply_temp:.1f}C\n" if supply_temp else ""

            telegram_msg = (
                f"<b>UMR2 ALERT</b>\n\n"
                f"Error: {error_str}\n"
                f"{temp_info}"
                f"State: {data.get('state')}\n"
                f"Message: {data.get('message')}\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            send_telegram_notification(telegram_msg)
    else:
        data['error'] = ''
        if state.last_error is not None:
            state.last_error = None
            if TELEGRAM_ENABLED:
                send_telegram_notification(
                    f"<b>UMR2 OK</b>\n\nSystem returned to normal."
                )

    log_to_csv(data, LOG_FILE)
    print(format_status_line(data, state, has_error, errors))

    return data


def test_connection() -> bool:
    """Test connection to UMR2 and display current status."""
    print(f"Testing connection to UMR2 at http://{UMR_IP}/...")
    print()

    raw_data = fetch_status()

    if raw_data is None:
        print(f"{Colors.RED}FAILED{Colors.RESET} Could not connect to UMR2 at {UMR_IP}")
        print("Check that:")
        print(f"  - The UMR2 is powered on")
        print(f"  - The IP address {UMR_IP} is correct")
        print(f"  - Your computer is on the same network")
        return False

    print(f"{Colors.GREEN}Connection OK!{Colors.RESET}")
    print()

    data = parse_status_data(raw_data)
    errors = detect_errors(data)

    supply_temp = data.get('supply_temp')
    return_temp = data.get('return_temp')

    print("Current Status:")
    print("-" * 50)
    print(f"  Supply temp:    {format_temp(supply_temp)} (aanvoer)")
    print(f"  Return temp:    {format_temp(return_temp)} (retour)")
    print(f"  State:          {data.get('state', '?')}")
    print(f"  Message:        {data.get('message', '?')}")
    print(f"  Mode:           {data.get('mode', '?')}")
    print(f"  Heating factor: {data.get('heating_factor', '?')}")
    print(f"  Cooling factor: {data.get('cooling_factor', '?')}")
    print(f"  Pump speed:     {data.get('pump_speed', '?')}")
    print(f"  Heater (CV):    {data.get('heater_state', '?')}")
    print(f"  Cooler (KM):    {data.get('cooler_state', '?')}")
    print("-" * 50)

    print()
    print(f"{Colors.YELLOW}E10 Limit:{Colors.RESET} Supply temp > {E10_TEMP_LIMIT}C triggers E10 error")

    if supply_temp is not None:
        margin = E10_TEMP_LIMIT - supply_temp
        if margin > 0:
            print(f"  Current margin: {margin:.1f}C below limit")
        else:
            print(f"  {Colors.RED}OVER LIMIT by {-margin:.1f}C!{Colors.RESET}")
    print()

    if errors:
        print(f"{Colors.RED}ERRORS DETECTED:{Colors.RESET}")
        for error in errors:
            print(f"  - {error}")
    else:
        print(f"{Colors.GREEN}No errors detected{Colors.RESET}")

    return True


def run_monitor():
    """Main monitoring loop."""
    state = MonitorState()

    print(f"{Colors.BOLD}UMR2 Pro Monitor{Colors.RESET}")
    print(f"Target: http://{UMR_IP}/")
    print(f"Poll interval: {POLL_INTERVAL} seconds")
    print(f"Log file: {LOG_FILE}")
    print(f"Telegram: {'Enabled' if TELEGRAM_ENABLED else 'Disabled'}")
    print(f"E10 limit: {E10_TEMP_LIMIT}C")
    print()
    print("-" * 60)
    print()

    try:
        while True:
            poll_once(state)
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print()
        print(f"\n{Colors.YELLOW}Monitoring stopped.{Colors.RESET}")
        print(f"Total polls: {state.poll_count}")
        print(f"Total errors detected: {state.error_count}")
        print(f"Data logged to: {LOG_FILE}")


def main():
    """Main entry point."""
    global UMR_IP, POLL_INTERVAL

    parser = argparse.ArgumentParser(
        description="UMR2 Pro Monitoring System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python umr2_monitor.py              Start monitoring
  python umr2_monitor.py --test       Test connection and show status

Note:
  Monitors supply temperature (aanvoertemperatuur) and triggers E10 alert
  when it exceeds 55C. Also monitors state/message fields for error codes.
        """
    )

    parser.add_argument(
        '--test', '-t',
        action='store_true',
        help='Test connection and display current status'
    )

    parser.add_argument(
        '--ip',
        type=str,
        help=f'Override UMR2 IP address (default: {UMR_IP})'
    )

    parser.add_argument(
        '--interval',
        type=int,
        help=f'Override poll interval in seconds (default: {POLL_INTERVAL})'
    )

    args = parser.parse_args()

    if args.ip:
        UMR_IP = args.ip
    if args.interval:
        POLL_INTERVAL = args.interval

    if args.test:
        success = test_connection()
        sys.exit(0 if success else 1)
    else:
        run_monitor()


if __name__ == "__main__":
    main()
