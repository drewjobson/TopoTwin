import time
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderServiceError

# US Bounding Box roughly containing continental US, Alaska, and Hawaii
US_BOUNDS = {
    "lat_min": 18.9,
    "lat_max": 72.0,
    "lon_min": -180.0,
    "lon_max": -66.0
}

import re

def clean_address(address: str) -> str:
    """Cleans an address by stripping out unit/apartment/suite/floor designations
    which can fail geocoding and parcel boundary lookup.
    """
    # Regex to match sub-unit indicators
    # Examples: 'Apt 2', 'Apartment B', 'Unit 4C', 'Suite 100', 'Fl 2', 'Floor 3', 'Bldg B', 'Building 2', '#12', '# 4'
    pattern = r'(?i)\b(apt|apartment|unit|suite|ste|fl|floor|dept|room|rm|bldg|building|box|p\.?o\.?\s*box)\s*#?\s*[a-zA-Z0-9-]+|\b#\s*[a-zA-Z0-9-]+'
    
    cleaned = re.sub(pattern, '', address)
    
    # Clean up multiple commas, trailing/leading commas, and whitespace
    cleaned = re.sub(r',\s*,', ',', cleaned) # Replace double commas
    cleaned = re.sub(r'\s+', ' ', cleaned)    # Collapse whitespace
    cleaned = cleaned.strip().strip(',')      # Strip leading/trailing spaces and commas
    cleaned = re.sub(r',\s*,', ',', cleaned) # Clean again
    cleaned = cleaned.strip()
    
    return cleaned

def geocode_address(address: str, user_agent: str = "topotwin_agent") -> tuple[float, float, str]:
    """Resolves an address string into (latitude, longitude, display_name).
    
    Args:
        address (str): Address to geocode.
        user_agent (str): User agent for OSM Nominatim API.
        
    Returns:
        tuple[float, float, str]: Latitude, Longitude, and formatted display name.
        
    Raises:
        ValueError: If address cannot be resolved or is outside the US.
        GeocoderServiceError: If the geocoding service fails.
    """
    if not address.strip():
        raise ValueError("Address cannot be empty.")

    cleaned_address = clean_address(address)
    if cleaned_address != address:
        print(f"  Cleaned address: '{address}' -> '{cleaned_address}'")
        address = cleaned_address

    geolocator = Nominatim(user_agent=user_agent)
    
    # Try geocoding with up to 3 retries (Nominatim can be occasionally rate-limited)
    last_err = None
    for attempt in range(3):
        try:
            location = geolocator.geocode(address, timeout=10)
            if location:
                lat, lon = location.latitude, location.longitude
                
                # Check if it falls inside US bounds (since USGS EPQS is US-only)
                if not (US_BOUNDS["lat_min"] <= lat <= US_BOUNDS["lat_max"] and 
                        US_BOUNDS["lon_min"] <= lon <= US_BOUNDS["lon_max"]):
                    raise ValueError(
                        f"Resolved location ({lat}, {lon}) is outside the United States. "
                        "The USGS Elevation service only covers the US."
                    )
                
                return lat, lon, location.address
            else:
                raise ValueError(f"Could not resolve address: '{address}'")
        except GeocoderServiceError as e:
            last_err = e
            time.sleep(1)
            
    raise GeocoderServiceError(f"Geocoding service error after 3 attempts: {last_err}")

if __name__ == "__main__":
    # Test geocoder
    try:
        lat, lon, name = geocode_address("Clinton, CT")
        print(f"Success! Name: {name}")
        print(f"Coordinates: {lat}, {lon}")
    except Exception as e:
        print(f"Test failed: {e}")
