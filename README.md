# UMR2 Pro Monitoring System

Monitor your WTH UMR2 Pro underfloor heating controller via its web interface. Logs data to CSV, detects errors (especially E10 - supply temperature too high), and generates graphs.

## Features

- **Continuous monitoring** - Polls status every 60 seconds
- **CSV logging** - All data saved for analysis
- **Error detection** - Alerts on E10 and other error codes
- **Live console output** - Compact status display
- **Graph generation** - Temperature and system status plots
- **Optional Telegram alerts** - Get notified on errors

## Installation

```bash
# Clone or copy files
cd ~/projects
mkdir umr2-monitor && cd umr2-monitor

# Install dependencies
pip install -r requirements.txt
```

## Quick Start

```bash
# Test connection to your UMR2
python umr2_monitor.py --test

# Start monitoring
python umr2_monitor.py

# After collecting data, generate graphs
python umr2_graphs.py
```

## Usage

### Monitor Script

```bash
# Start continuous monitoring
python umr2_monitor.py

# Test connection and show current status
python umr2_monitor.py --test

# Override IP address
python umr2_monitor.py --ip 192.168.1.100

# Override poll interval (seconds)
python umr2_monitor.py --interval 30
```

Console output:
```
[09:15:32] OK | Supply: 27.5C | Return: 27C | Pump: 0 | Factor: 0% | CV: off | Polls: 15 | Errors: 0
[09:16:32] ERROR | Supply: 56.2C | Return: 35C | Pump: 85 | Factor: 100% | CV: on | Polls: 16 | Errors: 1
  WARNING: E10
```

### Graph Script

```bash
# Show graphs for last 24 hours
python umr2_graphs.py

# Show last 48 hours
python umr2_graphs.py --hours 48

# Show last week
python umr2_graphs.py --hours 168

# Show all data
python umr2_graphs.py --hours 0

# Save as PNG instead of displaying
python umr2_graphs.py --save

# Text summary only (no graphs)
python umr2_graphs.py --summary

# Only temperature graph
python umr2_graphs.py --temp-only

# Only system status graph
python umr2_graphs.py --status-only
```

## Configuration

Edit the configuration section at the top of `umr2_monitor.py`:

```python
UMR_IP = "192.168.1.185"      # Your UMR2 IP address
POLL_INTERVAL = 60            # Seconds between polls
LOG_FILE = "umr2_log.csv"     # Where to save data
ERROR_LOG_FILE = "umr2_errors.log"

# Optional Telegram notifications
TELEGRAM_ENABLED = False
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""
```

### Telegram Setup (Optional)

1. Create a bot via [@BotFather](https://t.me/botfather)
2. Get your chat ID via [@userinfobot](https://t.me/userinfobot)
3. Update the configuration:

```python
TELEGRAM_ENABLED = True
TELEGRAM_BOT_TOKEN = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
TELEGRAM_CHAT_ID = "987654321"
```

## Error Codes

| Code | Description |
|------|-------------|
| E10 | Supply temperature too high (>55C) - **CRITICAL** |
| E11 | Return temperature too high |
| E21 | Sensor fault |
| E22 | Sensor fault |
| E30 | Communication error |
| E90 | Internal error |

## Output Files

| File | Description |
|------|-------------|
| `umr2_log.csv` | All monitoring data |
| `umr2_errors.log` | Error events only |
| `umr2_temperature_*.png` | Temperature graph (when saved) |
| `umr2_status_*.png` | System status graph (when saved) |

## CSV Structure

The log file contains these columns:

- `timestamp` - ISO 8601 timestamp
- `supply_temp` - Supply temperature (C)
- `return_temp` - Return temperature (C)
- `pump` - Pump value (0-100)
- `heating_factor` - Heating factor (%)
- `cooling_factor` - Cooling factor (%)
- `operating_mode` - Operating mode (verwarmen/koelen)
- `cv_status` - Central heating status (aan/uit)
- `cooling_machine` - Cooling machine status
- `max_protection` - Max protection status (OK or error)
- `return_limitation` - Return limitation status
- `condensation_protection` - Condensation protection status
- `status_display` - Status display text
- `status_description` - Status description
- `error` - Detected errors (if any)
- `thermostat_1` to `thermostat_10` - Thermostat states
- `output_1` to `output_10` - Output values

## Running as a Service

To run the monitor automatically on startup (Linux with systemd):

```bash
# Copy service file
sudo cp umr2-monitor.service /etc/systemd/system/

# Edit the service file to match your paths
sudo nano /etc/systemd/system/umr2-monitor.service

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable umr2-monitor
sudo systemctl start umr2-monitor

# Check status
sudo systemctl status umr2-monitor

# View logs
journalctl -u umr2-monitor -f
```

## Troubleshooting

### Cannot connect to UMR2

1. Verify the IP address: `ping 192.168.1.185`
2. Check if web interface is accessible: `curl http://192.168.1.185/`
3. Ensure you're on the same network
4. Check if UMR2 is powered on

### No data in graphs

1. Run the monitor first to collect data
2. Check that `umr2_log.csv` exists and has data
3. Try `--hours 0` to see all available data

### Parsing errors

The HTML structure may vary by firmware version. If values aren't being extracted correctly, you may need to adjust the regex patterns in the `FIELD_PATTERNS` list.

## Dependencies

- Python 3.7+
- requests - HTTP requests
- pandas - Data processing
- matplotlib - Graph generation

## License

MIT License
