#!/usr/bin/env python3
import warnings
warnings.filterwarnings('ignore', message='.*OpenSSL.*')

from datetime import datetime, time, timedelta
import logging
from typing import List, Tuple
import requests
import sys
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',  # Simplified format, we'll add timestamps manually
    handlers=[
        logging.FileHandler(config.LOG_TO)
    ]
)
logger = logging.getLogger(__name__)

# Configuration
class Config:
    # Use all settings from config file
    API_BASE_URL = config.API_BASE_URL
    PRICE_ZONE = config.PRICE_ZONE
    TIBBER_ADDON = config.TIBBER_ADDON
    VAT = config.VAT
    
    # Calculate required margin based on grid cost and efficiency
    MARGIN_REQUIRED = config.GRID_COST * (1 - config.SYSTEM_EFFICIENCY)

def get_price_data() -> List[dict]:
    """Fetch price data from API for tomorrow."""
    tomorrow = datetime.now().date() + timedelta(days=1)
    
    url = f"{Config.API_BASE_URL}/{tomorrow.year}/{tomorrow.strftime('%m-%d')}_{Config.PRICE_ZONE}.json"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch prices for {tomorrow}: {e}")
        sys.exit(1)

def calculate_total_price(spot_price: float) -> float:
    """Calculate total price including Tibber fee and VAT."""
    spot_ore = spot_price * 100
    price_before_vat = spot_ore + Config.TIBBER_ADDON/Config.VAT
    return price_before_vat * Config.VAT

def find_charge_discharge_hours(prices: List[dict]) -> Tuple[List[datetime], List[datetime]]:
    """Find optimal hours for charging and discharging."""
    price_times = []
    for hour in prices:
        time_start = datetime.fromisoformat(hour["time_start"].replace('Z', '+00:00')).astimezone()
        total_price = calculate_total_price(hour["SEK_per_kWh"])
        price_times.append((time_start, total_price))
        logger.debug(f"Price for {time_start.strftime('%H:%M')}: {total_price:.1f} öre/kWh")
    
    if not price_times:
        logger.error("No price data available")
        sys.exit(1)
    
    # Sort chronologically
    price_times.sort(key=lambda x: x[0])
    
    # Find all potential charging blocks (up to 3 consecutive hours each)
    charging_blocks = []
    
    # Look at each hour as a potential start of a charging block
    for i in range(len(price_times)):
        # Try to build a block of up to 3 consecutive hours
        block_times = []
        block_prices = []
        
        # Add up to 3 consecutive hours to this block
        for j in range(3):  # Try to make each block 3 hours if possible
            if i + j >= len(price_times):
                break
                
            # Stop if we cross midnight
            if j > 0 and price_times[i+j][0].day != price_times[i][0].day:
                break
                
            # Stop if hours aren't consecutive
            if j > 0 and price_times[i+j][0] - block_times[-1] != timedelta(hours=1):
                break
                
            block_times.append(price_times[i+j][0])
            block_prices.append(price_times[i+j][1])
        
        if block_times:  # If we found at least one hour
            avg_price = sum(block_prices) / len(block_prices)
            
            # Find discharge opportunities after this block
            discharge_options = [
                (t, p) for t, p in price_times[i+len(block_times):]
                if p >= avg_price + Config.MARGIN_REQUIRED
            ]
            
            if discharge_options:
                charging_blocks.append({
                    'times': block_times,
                    'avg_price': avg_price,
                    'discharge_options': discharge_options
                })
    
    # Sort blocks by average price and start time
    charging_blocks.sort(key=lambda x: (x['avg_price'], x['times'][0].hour))
    
    all_charge_hours = []
    all_discharge_hours = []
    used_hours = set()
    
    # Add logging for block selection - sort by time for logging
    sorted_for_log = sorted(charging_blocks, key=lambda x: x['times'][0])
    logger.info("Found charging blocks (chronological order):")
    for block in sorted_for_log:
        times = [t.strftime('%H:%M') for t in block['times']]
        logger.info(
            f"  {'-'.join(times)}, "
            f"avg price: {block['avg_price']:.1f} öre/kWh, "
            f"discharge options: {len(block['discharge_options'])} hours"
        )
    logger.info("")

    # Keep track of decisions for logging
    decisions = []
    
    # Keep trying blocks until we've processed all profitable opportunities
    for block in charging_blocks:
        # Skip if any hours are already used
        if any(t in used_hours for t in block['times']):
            logger.debug(f"Skipping block {block['times'][0].strftime('%H:%M')}, hours already used")
            continue
        
        # Add charging hours (each block can be up to 3 hours)
        all_charge_hours.extend(block['times'])
        used_hours.update(block['times'])
        
        # Add discharge hours
        discharge_times = [t for t, _ in block['discharge_options'] if t not in used_hours]
        all_discharge_hours.extend(discharge_times)
        used_hours.update(discharge_times)
        
        # Store decision for later logging
        decision = {
            'charge_times': block['times'],
            'charge_price': block['avg_price'],
            'discharge_times': discharge_times
        }
        decisions.append(decision)
    
    # Log decisions in chronological order
    logger.info("Selected charge/discharge pairs (chronological order):")
    for decision in sorted(decisions, key=lambda x: x['charge_times'][0]):
        times = [t.strftime('%H:%M') for t in decision['charge_times']]
        logger.info(
            f"Charging: {'-'.join(times)}, "
            f"avg price: {decision['charge_price']:.1f} öre/kWh"
        )
        
        if decision['discharge_times']:
            # Group consecutive discharge hours
            discharge_groups = []
            current_group = [decision['discharge_times'][0]]
            
            for t in decision['discharge_times'][1:]:
                if t - current_group[-1] == timedelta(hours=1):
                    current_group.append(t)
                else:
                    discharge_groups.append(current_group)
                    current_group = [t]
            discharge_groups.append(current_group)
            
            # Log each discharge group
            for group in discharge_groups:
                start = group[0]
                end = group[-1] + timedelta(hours=1)
                # Calculate average price for this discharge period
                discharge_prices = [p for t, p in price_times if t in group]
                avg_discharge_price = sum(discharge_prices) / len(discharge_prices)
                logger.info(
                    f"Discharging: {start.strftime('%H:%M')}-{end.strftime('%H:%M')}, "
                    f"avg price: {avg_discharge_price:.1f} öre/kWh"
                )
        logger.info("")
    
    # Remove any discharge hours that would overlap with charging
    all_discharge_hours = [
        t for t in sorted(all_discharge_hours)
        if t not in all_charge_hours
    ]
    
    return (sorted(all_charge_hours), sorted(all_discharge_hours))

def main() -> None:
    """Main function."""
    try:
        # Log start of run
        now = datetime.now()
        tomorrow = now.date() + timedelta(days=1)
        logger.info(f"\n=== Starting price analysis at {now.strftime('%Y-%m-%d %H:%M:%S')} ===")
        logger.info(f"Analyzing prices for: {tomorrow.strftime('%Y-%m-%d')}\n")
        
        prices = get_price_data()
        charge_hours, discharge_hours = find_charge_discharge_hours(prices)
        
        # Combine all events and sort chronologically
        all_events = [(t, '+') for t in charge_hours] + [(t, '-') for t in discharge_hours]
        all_events.sort(key=lambda x: x[0])  # Sort by time
        
        # Group consecutive hours with same action
        groups = []
        if all_events:
            current_group = [all_events[0]]
            
            for event in all_events[1:]:
                if (event[0] - current_group[-1][0] == timedelta(hours=1) and 
                    event[1] == current_group[-1][1]):
                    current_group.append(event)
                else:
                    groups.append(current_group)
                    current_group = [event]
            groups.append(current_group)
        
        # Log summary of decisions
        logger.info("\nFinal schedule:")
        for block in groups:
            start = block[0][0]
            end = block[-1][0] + timedelta(hours=1)
            action = "Charging" if block[0][1] == '+' else "Discharging"
            end_str = "23:59" if (block[-1][0].hour == 23 or end.hour == 0) else end.strftime('%H:%M')
            logger.info(f"{action}: {start.strftime('%H:%M')}-{end_str}")
        
        # Log end of run
        logger.info(f"\n=== Completed price analysis at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        
        # Print schedule to console (unchanged)
        for group in groups:
            start = group[0][0]
            end = group[-1][0] + timedelta(hours=1)
            action = group[0][1]
            is_last_hour = group[-1][0].hour == 23 or end.hour == 0
            end_str = "23:59" if is_last_hour else end.strftime('%H:%M')
            print(f"{start.strftime('%H:%M')}-{end_str}/1234567/{action}")
        
    except Exception as e:
        logger.error(f"\n!!! Error occurred at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()