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
    
    # Find all possible charging blocks
    charging_options = []
    for i in range(len(price_times) - 2):  # Look at 3-hour windows
        times = []
        prices = []
        
        # Try to get 3 consecutive hours
        valid_block = True
        for j in range(3):
            if i + j >= len(price_times):
                valid_block = False
                break
            if j > 0 and price_times[i+j][0].day != price_times[i+j-1][0].day:
                valid_block = False
                break
            times.append(price_times[i+j][0])
            prices.append(price_times[i+j][1])
        
        if valid_block:
            avg_price = sum(prices) / len(prices)
            charging_options.append((times, avg_price, prices))
        
        # Only add shorter blocks if they're significantly cheaper
        elif len(times) >= 2:
            avg_price = sum(prices) / len(times)
            if avg_price < min(prices) * 0.9:  # At least 10% cheaper than any individual hour
                charging_options.append((times, avg_price, prices))
    
    # Sort charging options by price
    charging_options.sort(key=lambda x: x[1])
    
    all_charge_hours = []
    all_discharge_hours = []
    
    # Try each charging block, starting with the cheapest
    for charge_times, charge_avg_price, charge_prices in charging_options:
        charge_end = charge_times[-1]
        
        # Find potential discharge hours after this charging block
        discharge_candidates = [
            (t, p) for t, p in price_times 
            if t > charge_end and p >= charge_avg_price + Config.MARGIN_REQUIRED
        ]
        
        if not discharge_candidates:
            continue
        
        # Find consecutive profitable discharge periods
        best_discharge = None
        max_profit = 0
        
        i = 0
        while i < len(discharge_candidates):
            current_seq = [discharge_candidates[i][0]]
            current_profit = discharge_candidates[i][1]
            
            j = i + 1
            while j < len(discharge_candidates):
                if discharge_candidates[j][0] - current_seq[-1] == timedelta(hours=1):
                    current_seq.append(discharge_candidates[j][0])
                    current_profit += discharge_candidates[j][1]
                    if len(current_seq) <= len(charge_times) * 3:  # Each charge hour can support up to 3 discharge hours
                        if current_profit > max_profit:
                            max_profit = current_profit
                            best_discharge = current_seq.copy()
                else:
                    break
                j += 1
            i = j
        
        # Skip if charging period is too short for discharge period
        if best_discharge and len(charge_times) * 3 < len(best_discharge):
            continue
        
        if best_discharge:
            # Check if this cycle overlaps with existing cycles
            overlaps = False
            for t in charge_times + best_discharge:
                if t in all_charge_hours or t in all_discharge_hours:
                    overlaps = True
                    break
            
            if not overlaps:
                all_charge_hours.extend(charge_times)
                all_discharge_hours.extend(best_discharge)
                continue
    
    return (sorted(all_charge_hours), sorted(all_discharge_hours))

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