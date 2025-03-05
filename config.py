# API Configuration
API_BASE_URL = "https://www.elprisetjustnu.se/api/v1/prices"
PRICE_ZONE = "SE3"  # Stockholm price zone

# Price components (öre/kWh)
TIBBER_ADDON = 8.6  # Tibber's fee including VAT
VAT = 1.25  # 25% VAT
GRID_COST = 86.375  # Grid cost, adjust as needed when it changes

# System efficiency
# Research shows home battery systems typically claim 90-95% round-trip efficiency
# Using conservative 85.7% based on real-world measurements:
# - Charging: 92.6% (10.8kWh in -> 10kWh stored)
# - Discharging: 92.6% (estimated same losses)
# - Total round-trip: 85.7% (92.6% × 92.6%)
SYSTEM_EFFICIENCY = 0.857

# Logging configuration
LOG_TO = "laddtider.log" 