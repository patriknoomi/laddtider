#!/usr/bin/env python3
import warnings
warnings.filterwarnings('ignore', message='.*OpenSSL.*')

from datetime import datetime, time, timedelta
import logging
from typing import List, Tuple
import requests
import sys

# Configure logging
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
class Config:
    # Base URL for the API
    API_BASE_URL = "https://www.elprisetjustnu.se/api/v1/prices"
    PRICE_ZONE = "SE3"  # Stockholm price zone
    
    # Price components (öre/kWh)
    TIBBER_PÅSLAG = 8.6  # Tibber's fee including VAT
    MOMS = 1.25  # 25% VAT
    
    # Price margin required for profitable discharge (includes battery efficiency losses)
    MARGIN_REQUIRED = 25  # öre/kWh (0.25 SEK/kWh)
    
    # Number of hours to charge
    CHARGE_HOURS = 3

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
    price_before_vat = spot_ore + Config.TIBBER_PÅSLAG/Config.MOMS
    return price_before_vat * Config.MOMS

def find_charge_discharge_hours(prices: List[dict]) -> Tuple[List[datetime], List[datetime]]:
    """Find optimal hours for charging and discharging."""
    price_times = []
    for hour in prices:
        time_start = datetime.fromisoformat(hour["time_start"].replace('Z', '+00:00')).astimezone()
        total_price = calculate_total_price(hour["SEK_per_kWh"])
        price_times.append((time_start, total_price))
    
    if not price_times:
        logger.error("No price data available")
        sys.exit(1)
    
    # Sort chronologically
    price_times.sort(key=lambda x: x[0])
    
    # Split day into potential charging periods (avoiding midnight crossing)
    day_segments = [
        # Night/early morning: 00:00-05:00
        [(t, p) for t, p in price_times if 0 <= t.hour < 5],
        # Morning/afternoon: 12:00-16:00
        [(t, p) for t, p in price_times if 12 <= t.hour < 16],
    ]
    
    charge_blocks = []  # Store (block, avg_price) tuples
    discharge_candidates = set()  # Use a set to avoid duplicates
    
    # For each segment, find the best charging block and subsequent discharge hours
    for segment in day_segments:
        if len(segment) < 3:  # Need at least 3 hours for charging
            continue
            
        # Find cheapest 3 consecutive hours in this segment
        cheapest_block = None
        cheapest_price = float('inf')
        
        for i in range(len(segment) - 2):
            block_times = [segment[i+j][0] for j in range(3)]
            block_prices = [segment[i+j][1] for j in range(3)]
            avg_price = sum(block_prices) / 3
            
            if avg_price < cheapest_price:
                cheapest_price = avg_price
                cheapest_block = block_times
        
        if cheapest_block:
            charge_blocks.append((cheapest_block, cheapest_price))
    
    # Sort charge blocks by time
    charge_blocks.sort(key=lambda x: x[0][0])  # Sort by start time of block
    
    all_charge_hours = []
    
    # Process charge blocks in chronological order
    for block, avg_price in charge_blocks:
        all_charge_hours.extend(block)
        
        # Find discharge hours after this charging block
        charge_end_time = block[-1]
        min_discharge_price = avg_price + Config.MARGIN_REQUIRED
        
        # Add discharge candidates to set
        discharge_candidates.update(
            t for t, p in price_times 
            if t > charge_end_time and p >= min_discharge_price
        )
    
    return (all_charge_hours, sorted(discharge_candidates))

def format_output(times: List[datetime], action: str) -> None:
    """Format and print charging/discharging schedule."""
    if not times:
        return
    
    # Group consecutive hours
    groups = []
    current_group = [times[0]]
    
    for t in times[1:]:
        if t - current_group[-1] == timedelta(hours=1):
            current_group.append(t)
        else:
            groups.append(current_group)
            current_group = [t]
    groups.append(current_group)
    
    # Print each group with today's date
    today = datetime.now().date()
    for group in groups:
        start = group[0]
        end = group[-1] + timedelta(hours=1)
        print(f"{today.strftime('%Y-%m-%d')} {start.strftime('%H:%M')}-{end.strftime('%H:%M')}/1234567/{action}")

def main() -> None:
    """Main function."""
    try:
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
        
        # Print each group (time range only)
        for group in groups:
            start = group[0][0]
            end = group[-1][0] + timedelta(hours=1)
            action = group[0][1]
            print(f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}/1234567/{action}")
        
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()