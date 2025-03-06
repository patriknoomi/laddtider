# Laddtider (Charging Times)

A Python utility for optimizing home battery charging/discharging schedules based on hourly electricity prices in Sweden.

## Overview

This tool analyzes tomorrow's electricity prices (from elprisetjustnu.se) and determines optimal times for:
- Charging the home battery during low-price periods
- Discharging the battery during high-price periods

The algorithm considers:
- Battery charging efficiency (~92.6%)
- Grid costs
- Tibber's fees and VAT
- Minimum profit margins for discharge

## How It Works

The algorithm:
1. Fetches tomorrow's electricity prices
2. Finds potential charging blocks (1-3 consecutive hours)
3. Calculates profitability including:
   - Battery efficiency losses
   - Grid costs both ways
   - Tibber fees and VAT
4. Pairs charging blocks with profitable discharge periods
5. Outputs an optimized schedule

## Features

- Finds optimal charging blocks (1-3 consecutive hours)
- Pairs charging blocks with profitable discharge periods
- Handles multiple charge/discharge cycles per day
- Detailed logging of decisions and price analysis
- Configurable parameters (grid costs, efficiency, etc.)

## Usage

```bash
python laddtider.py
```

Output format:
```
HH:MM-HH:MM/1234567/+  # Charging period
HH:MM-HH:MM/1234567/-  # Discharging period
```

Example output:
```
02:00-05:00/1234567/+
06:00-10:00/1234567/-
11:00-14:00/1234567/+
16:00-23:59/1234567/-
```

### Logging

The script maintains a detailed log (laddtider.log) showing:
```
=== Starting price analysis at 2024-01-20 23:34:46 ===
Analyzing prices for: 2024-01-21

Found charging blocks (chronological order):
  00:00-01:00-02:00, avg price: 11.5 öre/kWh, discharge options: 12 hours
  ...

Selected charge/discharge pairs (chronological order):
Charging: 02:00-03:00-04:00, avg price: 10.7 öre/kWh
Discharging: 06:00-10:00, avg price: 71.6 öre/kWh
...

Final schedule:
Charging: 02:00-05:00
Discharging: 06:00-10:00
...
```

## Configuration

Edit `config.py` to adjust:
- Grid costs (öre/kWh)
- System efficiency (default 85.7% round-trip)
- Tibber addon and VAT rates
- Logging preferences

### Price Components
- Grid cost: Fixed cost for using the power grid
- Tibber addon: Supplier's fee including VAT
- VAT: 25% on all components
- System efficiency: Conservative 85.7% based on real measurements

## Requirements

- Python 3.x
- `requests` library

## Installation

1. Clone the repository
2. Install requirements:
   ```bash
   pip install requests
   ```

## Files

- `laddtider.py` - Main script with sophisticated charging strategy
- `laddtider_simple.py` - Simplified version for testing/comparison
- `config.py` - Configuration parameters
- `laddtider.log` - Detailed decision logs

## Error Handling

The script handles several error conditions:
- API unavailability
- Missing price data
- Invalid time formats
- Network issues

Error messages are logged to both console and log file.

## Future Plans

- Home Assistant integration for automated scheduling
- Real-time price monitoring
- Performance analysis and reporting
- Support for different price zones (SE1-SE4)
- Command-line configuration options

## License

MIT License 