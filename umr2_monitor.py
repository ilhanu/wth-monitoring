#!/usr/bin/env python3
"""
UMR2 Pro Monitoring System
Monitors a WTH UMR2 Pro underfloor heating controller via its web interface.

Features:
- Polls status every 60 seconds
- Logs all data to CSV
- Alerts on E10 errors (supply temperature >55°C)
- Optional Telegram notifications
"""

import argparse
import csv
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

# =============================================================================
# Configuration
# =============================================================================

UMR_IP = "192.168.1.185"
UMR_URL = f"http://{UMR_IP}/"
POLL_INTERVAL = 60  # seconds
LOG_FILE = "umr2_log.csv"
ERROR_LOG_FILE = "umr2_errors.log"
REQUEST_TIMEOUT = 10  # seconds

# Optional Telegram notifications
TELEGRAM_ENABLED = False
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""

# Error codes to detect
ERROR_CODES = ["E10", "E11", "E21", "E22", "E30", "E90"]
E10_TEMP_LIMIT = 55.0  # °C

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
# HTML Parsing Patterns
# =============================================================================

# Regex patterns to extract values from UMR2 HTML
# Format: (pattern, field_name)
FIELD_PATTERNS = [
    (r'Aanvoertemp[^<]*</div>\s*<input[^>]*value="([^"]*)"', 'supply_temp'),
    (r'Retourtemp[^<]*</div>\s*<input[^>]*value="([^"]*)"', 'return_temp'),
    (r'>Pomp<[^<]*</div>\s*<input[^>]*value="([^"]*)"', 'pump'),
    (r'Verwarm\.?factor[^<]*</div>\s*<input[^>]*value="([^"]*)"', 'heating_factor'),
    (r'Koel\s*factor[^<]*</div>\s*<input[^>]*value="([^"]*)"', 'cooling_factor'),
    (r'Bedrijfsmodus[^<]*</div>\s*<input[^>]*value="([^"]*)"', 'operating_mode'),
    (r'>CV<[^<]*</div>\s*<input[^>]*value="([^"]*)"', 'cv_status'),
    (r'Koelmachine[^<]*</div>\s*<input[^>]*value="([^"]*)"', 'cooling_machine'),
    (r'Maximaal\s*beveiliging[^<]*</div>\s*<input[^>]*value="([^"]*)"', 'max_protection'),
    (r'Retour\s*begrenzing[^<]*</div>\s*<input[^>]*value="([^"]*)"', 'return_limitation'),
    (r'Condens\s*beveiliging[^<]*</div>\s*<input[^>]*value="([^"]*)"', 'condensation_protection'),
    (r'Status\s*\(display\)[^<]*</div>\s*<input[^>]*value="([^"]*)"', 'status_display'),
    (r'Status\s*\(toelichting\)[^<]*</div>\s*<input[^>]*value="([^"]*)"', 'status_description'),
]

# Thermostat and output patterns (1-10)
THERMOSTAT_PATTERN = r'Thermostaat\s*{n}[^<]*</div>\s*<input[^>]*value="([^"]*)"'
OUTPUT_PATTERN = r'Uitgang\s*{n}[^<]*</div>\s*<input[^>]*value="([^"]*)"'

# =============================================================================
# CSV Field Order
# =============================================================================

CSV_FIELDS = [
    'timestamp',
    'supply_temp',
    'return_temp',
    'pump',
    'heating_factor',
    'cooling_factor',
    'operating_mode',
    'cv_status',
    'cooling_machine',
    'max_protection',
    'return_limitation',
    'condensation_protection',
    'status_display',
    'status_description',
    'error',
    'thermostat_1', 'output_1',
    'thermostat_2', 'output_2',
    'thermostat_3', 'output_3',
    'thermostat_4', 'output_4',
    'thermostat_5', 'output_5',
    'thermostat_6', 'output_6',
    'thermostat_7', 'output_7',
    'thermostat_8', 'output_8',
    'thermostat_9', 'output_9',
    'thermostat_10', 'output_10',
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

def fetch_umr_html() -> Optional[str]:
    """Fetch HTML from UMR2 web interface."""
    try:
        response = requests.get(UMR_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        return None


def parse_umr_html(html: str) -> dict:
    """Parse UMR2 HTML and extract all status fields."""
    data = {}
    flags = re.IGNORECASE | re.DOTALL

    # Extract main fields
    for pattern, field_name in FIELD_PATTERNS:
        match = re.search(pattern, html, flags)
        data[field_name] = match.group(1).strip() if match else ""

    # Extract thermostat and output values (1-10)
    for n in range(1, 11):
        # Thermostat
        pattern = THERMOSTAT_PATTERN.replace('{n}', str(n))
        match = re.search(pattern, html, flags)
        data[f'thermostat_{n}'] = match.group(1).strip() if match else ""

        # Output
        pattern = OUTPUT_PATTERN.replace('{n}', str(n))
        match = re.search(pattern, html, flags)
        data[f'output_{n}'] = match.group(1).strip() if match else ""

    return data


def detect_errors(data: dict, html: str) -> list:
    """Detect error conditions from parsed data and raw HTML."""
    errors = []

    # Check max_protection status
    max_prot = data.get('max_protection', '').upper()
    if max_prot and max_prot != 'OK':
        errors.append(f"MAX_PROTECTION:{max_prot}")

    # Check status_description for error codes
    status_desc = data.get('status_description', '').upper()
    for code in ERROR_CODES:
        if code in status_desc:
            errors.append(code)

    # Check raw HTML for error codes (backup)
    for code in ERROR_CODES:
        if code in html and code not in errors:
            errors.append(code)

    # Check supply temperature for E10 condition
    try:
        supply_temp = float(data.get('supply_temp', '0').replace(',', '.'))
        if supply_temp > E10_TEMP_LIMIT:
            if 'E10' not in errors:
                errors.append(f"E10_THRESHOLD:{supply_temp}")
    except ValueError:
        pass

    return errors


def log_to_csv(data: dict, log_file: str):
    """Append data to CSV log file."""
    file_exists = os.path.exists(log_file)

    with open(log_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction='ignore')

        # Write header if file is new
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


def format_status_line(data: dict, state: MonitorState, has_error: bool, errors: list) -> str:
    """Format a compact status line for console output."""
    timestamp = datetime.now().strftime("%H:%M:%S")

    supply = data.get('supply_temp', '?')
    ret = data.get('return_temp', '?')
    pump = data.get('pump', '?')
    factor = data.get('heating_factor', '?')
    cv = data.get('cv_status', '?')

    # Translate CV status
    cv_display = 'on' if cv.lower() in ['aan', 'on', '1'] else 'off'

    if has_error:
        status_icon = f"{Colors.RED}ERROR{Colors.RESET}"
        error_str = ', '.join(errors)
        line = f"[{timestamp}] {status_icon} | Supply: {supply}°C | Return: {ret}°C | Pump: {pump} | Factor: {factor} | CV: {cv_display} | Polls: {state.poll_count} | Errors: {state.error_count}"
        line += f"\n  {Colors.YELLOW}WARNING:{Colors.RESET} {error_str}"
    else:
        status_icon = f"{Colors.GREEN}OK{Colors.RESET}"
        line = f"[{timestamp}] {status_icon} | Supply: {supply}°C | Return: {ret}°C | Pump: {pump} | Factor: {factor} | CV: {cv_display} | Polls: {state.poll_count} | Errors: {state.error_count}"

    return line


def format_connection_error_line(state: MonitorState) -> str:
    """Format a connection error status line."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    return f"[{timestamp}] {Colors.YELLOW}CONNECTION_ERROR{Colors.RESET} | Failed to reach UMR2 at {UMR_IP} | Polls: {state.poll_count} | Consecutive failures: {state.consecutive_failures}"


def poll_once(state: MonitorState) -> dict:
    """Perform a single poll of the UMR2."""
    state.poll_count += 1

    # Fetch HTML
    html = fetch_umr_html()

    if html is None:
        state.consecutive_failures += 1
        print(format_connection_error_line(state))

        # Log connection error
        error_data = {
            'timestamp': datetime.now().isoformat(),
            'error': 'CONNECTION_ERROR',
        }
        # Fill other fields with empty strings
        for field in CSV_FIELDS:
            if field not in error_data:
                error_data[field] = ''

        log_to_csv(error_data, LOG_FILE)
        return error_data

    state.consecutive_failures = 0

    # Parse data
    data = parse_umr_html(html)
    data['timestamp'] = datetime.now().isoformat()

    # Detect errors
    errors = detect_errors(data, html)
    has_error = len(errors) > 0

    if has_error:
        error_str = ', '.join(errors)
        data['error'] = error_str
        state.error_count += 1

        # Log to error file
        log_error(f"Errors detected: {error_str} | Supply: {data.get('supply_temp')}°C", ERROR_LOG_FILE)

        # Send Telegram notification for NEW errors only
        if state.last_error != error_str:
            state.last_error = error_str
            state.last_error_time = datetime.now()

            telegram_msg = (
                f"<b>UMR2 ALERT</b>\n\n"
                f"Error: {error_str}\n"
                f"Supply temp: {data.get('supply_temp')}°C\n"
                f"Return temp: {data.get('return_temp')}°C\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            send_telegram_notification(telegram_msg)
    else:
        data['error'] = ''
        # Clear last error when everything is OK
        if state.last_error is not None:
            state.last_error = None
            # Optionally notify that error is cleared
            if TELEGRAM_ENABLED:
                send_telegram_notification(
                    f"<b>UMR2 OK</b>\n\nSystem returned to normal.\n"
                    f"Supply temp: {data.get('supply_temp')}°C"
                )

    # Log to CSV
    log_to_csv(data, LOG_FILE)

    # Print status line
    print(format_status_line(data, state, has_error, errors))

    return data


def test_connection() -> bool:
    """Test connection to UMR2 and display current status."""
    print(f"Testing connection to UMR2 at {UMR_URL}...")
    print()

    html = fetch_umr_html()

    if html is None:
        print(f"{Colors.RED}FAILED{Colors.RESET} Could not connect to UMR2 at {UMR_IP}")
        print("Check that:")
        print(f"  - The UMR2 is powered on")
        print(f"  - The IP address {UMR_IP} is correct")
        print(f"  - Your computer is on the same network")
        return False

    print(f"{Colors.GREEN}Connection OK!{Colors.RESET}")
    print()

    # Parse and display status
    data = parse_umr_html(html)
    errors = detect_errors(data, html)

    print("Current Status:")
    print("-" * 50)
    print(f"  Supply temperature:     {data.get('supply_temp', '?')}°C")
    print(f"  Return temperature:     {data.get('return_temp', '?')}°C")
    print(f"  Pump:                   {data.get('pump', '?')}")
    print(f"  Heating factor:         {data.get('heating_factor', '?')}")
    print(f"  Cooling factor:         {data.get('cooling_factor', '?')}")
    print(f"  Operating mode:         {data.get('operating_mode', '?')}")
    print(f"  CV status:              {data.get('cv_status', '?')}")
    print(f"  Cooling machine:        {data.get('cooling_machine', '?')}")
    print(f"  Max protection:         {data.get('max_protection', '?')}")
    print(f"  Return limitation:      {data.get('return_limitation', '?')}")
    print(f"  Condensation protection:{data.get('condensation_protection', '?')}")
    print(f"  Status (display):       {data.get('status_display', '?')}")
    print(f"  Status (description):   {data.get('status_description', '?')}")
    print("-" * 50)

    # Show thermostats and outputs
    print("\nThermostats and Outputs:")
    for n in range(1, 11):
        therm = data.get(f'thermostat_{n}', '?')
        out = data.get(f'output_{n}', '?')
        if therm or out:  # Only show if we got data
            print(f"  Thermostat {n:2d}: {therm:>5s}  |  Output {n:2d}: {out}")

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
    print(f"Target: {UMR_URL}")
    print(f"Poll interval: {POLL_INTERVAL} seconds")
    print(f"Log file: {LOG_FILE}")
    print(f"Telegram notifications: {'Enabled' if TELEGRAM_ENABLED else 'Disabled'}")
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
    global UMR_IP, UMR_URL, POLL_INTERVAL

    parser = argparse.ArgumentParser(
        description="UMR2 Pro Monitoring System - Monitor your underfloor heating controller",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python umr2_monitor.py              Start monitoring
  python umr2_monitor.py --test       Test connection and show current status

Configuration:
  Edit the variables at the top of the script to change:
  - UMR_IP: IP address of your UMR2 controller
  - POLL_INTERVAL: How often to poll (seconds)
  - LOG_FILE: Where to save CSV data
  - TELEGRAM_*: Telegram notification settings
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

    # Apply overrides
    if args.ip:
        UMR_IP = args.ip
        UMR_URL = f"http://{UMR_IP}/"
    if args.interval:
        POLL_INTERVAL = args.interval

    if args.test:
        success = test_connection()
        sys.exit(0 if success else 1)
    else:
        run_monitor()


if __name__ == "__main__":
    main()
