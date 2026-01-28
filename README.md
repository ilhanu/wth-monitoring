# UMR2 Pro Monitoring System

Monitor your WTH UMR2 Pro underfloor heating controller via its JSON API. Logs data to CSV including temperatures, detects errors (E10 when supply temp >55°C), and generates graphs.

## Features

- **Continuous monitoring** - Polls status every 60 seconds via JSON API
- **Temperature tracking** - Logs supply (aanvoer) and return (retour) temperatures
- **CSV logging** - All data saved for analysis
- **E10 detection** - Alerts when supply temperature exceeds 55°C
- **Error detection** - Monitors state/message fields for all error codes
- **Live console output** - Compact status display with colors
- **Graph generation** - Temperature and system status plots with E10 limit line
- **Optional Telegram alerts** - Get notified on errors

## Installation

```bash
# Clone or copy files
cd ~/projects
mkdir umr2-monitor && cd umr2-monitor

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Quick Start

```bash
# Activate virtual environment
source venv/bin/activate

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
[09:15:32] OK | Supply: 27.5C | Return: 25.2C | Mode: verwarmen | Heat: 45% | Pump: 60 | CV: aan | Polls: 15
[09:16:32] ERROR | Supply: 56.2C | Return: 35.0C | Mode: verwarmen | Heat: 100% | Pump: 85 | CV: aan | Polls: 16
  ALERT: E10(temp:56.2C)
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

# E10 temperature limit
E10_TEMP_LIMIT = 55.0         # °C - supply temp above this triggers E10

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

## API Endpoints

The monitor uses the UMR2 JSON API:

| Endpoint | Description |
|----------|-------------|
| `get.json?f=$.status.main.*` | Main status (state, message, mode, factors) |
| `get.json?f=$.status.outputs.*` | Output status (heater, cooler, pump) |
| `get.json?f=$.status.inputs.max.*` | Supply temperature (aanvoertemperatuur) |
| `get.json?f=$.status.inputs.return.temperature` | Return temperature (retourtemperatuur) |

**Note:** The wildcard query `$.status.inputs.*` may not work on all devices. The monitor uses specific paths for temperature data.

## Error Codes

| Code | Description |
|------|-------------|
| E10 | Supply temperature too high (>55°C) - **CRITICAL** |
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

| Column | Description |
|--------|-------------|
| `timestamp` | ISO 8601 timestamp |
| `supply_temp` | Supply temperature in °C (aanvoertemperatuur) |
| `return_temp` | Return temperature in °C (retourtemperatuur) |
| `state` | System state (OK or error) |
| `message` | Status message (OK or error code like E10) |
| `mode` | Operating mode (verwarmen/koelen/uit) |
| `heating_factor` | Heating factor (0-100%) |
| `cooling_factor` | Cooling factor (0-100%) |
| `pump_speed` | Pump speed value |
| `heater_state` | Central heating status (aan/uit) |
| `cooler_state` | Cooling machine status (aan/uit) |
| `error` | Detected errors (if any) |

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

### Test the API endpoints

```bash
# Main status
curl "http://192.168.1.185/get.json?f=\$.status.main.*"

# Outputs status
curl "http://192.168.1.185/get.json?f=\$.status.outputs.*"

# Supply temperature (aanvoertemperatuur)
curl "http://192.168.1.185/get.json?f=\$.status.inputs.max.*"

# Return temperature
curl "http://192.168.1.185/get.json?f=\$.status.inputs.return.temperature"
```

### No data in graphs

1. Run the monitor first to collect data
2. Check that `umr2_log.csv` exists and has data
3. Try `--hours 0` to see all available data

### pip install error: "externally managed environment"

Use a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Dependencies

- Python 3.7+
- requests - HTTP requests
- pandas - Data processing
- matplotlib - Graph generation

## License

MIT License
