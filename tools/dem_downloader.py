import math
import json
import asyncio
import aiohttp
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
from pyproj import Transformer
from scipy.interpolate import griddata
from typing import Tuple, List, Optional, Dict, Any

from tools.context_resolver import resolve_context

# Endpoints
USGS_URL = resolve_context("[[USGS_URL]]")
CT_ELEVATION_URL = resolve_context("[[CT_ELEVATION_URL]]")
if "[[CT_ELEVATION_URL]]" in CT_ELEVATION_URL:
    CT_ELEVATION_URL = "https://cteco.uconn.edu/ctraster/rest/services/elevation/Statewide2023/ImageServer/getSamples"

class DEMDownloader:
    """
    Handles coordinate transformations and chunked asynchronous REST API fetching 
    from the UConn CT ECO 2023 LiDAR ImageServer.
    """
    
    # EPSG:4326 (WGS84 Lat/Lon) to EPSG:6434 (CT State Plane NAD83 2011 Feet)
    CRS_TRANSFORMER = Transformer.from_crs("EPSG:4326", "EPSG:6434", always_xy=True)
    
    def __init__(self, max_samples_per_request: int = 1000, max_concurrency: int = 5):
        # ArcGIS ImageServer hard limit is typically 1000 samples per request
        self.max_samples = max_samples_per_request
        self.max_concurrency = max_concurrency

    def generate_parcel_grid(self, 
                             polygon_bounds_epsg6434: Tuple[float, float, float, float], 
                             resolution_feet: float = 2.0) -> np.ndarray:
        """
        Calculates a bounding box and generates an evenly spaced coordinate grid 
        in native EPSG:6434 State Plane Feet.
        """
        min_x, min_y, max_x, max_y = polygon_bounds_epsg6434
        
        # Grid spacing
        x_coords = np.arange(min_x, max_x + resolution_feet, resolution_feet)
        y_coords = np.arange(min_y, max_y + resolution_feet, resolution_feet)
        
        xx, yy = np.meshgrid(x_coords, y_coords)
        return np.column_stack((xx.ravel(), yy.ravel()))

    async def _fetch_chunk(self, session: aiohttp.ClientSession, points_chunk: np.ndarray, retries: int = 3) -> List[float]:
        """
        Sends an HTTP POST payload for a specific chunk of coordinate points.
        Utilizes esriGeometryMultipoint specification.
        """
        geom_json = {
            "points": points_chunk.tolist(),
            "spatialReference": {"wkid": 6434}
        }
        
        payload = {
            "geometry": json.dumps(geom_json),
            "geometryType": "esriGeometryMultipoint",
            "returnFirstValueOnly": "true",
            "interpolation": "RSP_BilinearInterpolation",
            "f": "json"
        }
        
        for attempt in range(retries):
            try:
                # Add exponential backoff sleep
                if attempt > 0:
                    await asyncio.sleep(2 ** attempt + 0.1 * attempt)
                async with session.post(CT_ELEVATION_URL, data=payload, timeout=12) as response:
                    if response.status != 200:
                        raise ConnectionError(f"ImageServer API Error: Status {response.status}")
                        
                    data = await response.json()
                    elevations = []
                    
                    if "samples" in data:
                        for sample in data["samples"]:
                            val = sample.get("value", "-9999")
                            try:
                                elevations.append(float(val))
                            except ValueError:
                                elevations.append(-9999.0)
                    else:
                        elevations = [-9999.0] * len(points_chunk)
                        
                    return elevations
            except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError, ValueError) as e:
                if attempt == retries - 1:
                    return [-9999.0] * len(points_chunk)
                await asyncio.sleep(0.5 * (attempt + 1))

    async def download_elevations(self, grid_points_epsg6434: np.ndarray) -> np.ndarray:
        """
        Partitions the grid array into API-compliant chunks and concurrently fetches data.
        Mitigates anomalies. Returned elevations are in feet.
        """
        total_points = len(grid_points_epsg6434)
        chunks = [grid_points_epsg6434[i:i + self.max_samples] 
                  for i in range(0, total_points, self.max_samples)]
        
        elevations = []
        connector = aiohttp.TCPConnector(limit=self.max_concurrency)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Introduce 100ms dispatch jitter
            tasks = []
            for idx, chunk in enumerate(chunks):
                if idx > 0:
                    await asyncio.sleep(0.1)
                tasks.append(self._fetch_chunk(session, chunk))
            
            results = await asyncio.gather(*tasks)
            
            for res in results:
                elevations.extend(res)
                
        elevations_arr = np.array(elevations)
        
        # Anomaly Mitigation: Detect NoData flags (-9999) and interpolate via KD-Tree
        valid_mask = elevations_arr > -9000
        if not np.all(valid_mask):
            valid_points = grid_points_epsg6434[valid_mask]
            valid_elevs = elevations_arr[valid_mask]
            
            missing_points = grid_points_epsg6434[~valid_mask]
            if len(valid_points) > 0:
                interpolated_elevs = griddata(valid_points, valid_elevs, missing_points, method='nearest')
                elevations_arr[~valid_mask] = interpolated_elevs
            else:
                elevations_arr[~valid_mask] = 0.0
            
        return np.column_stack((grid_points_epsg6434, elevations_arr))

# --- Backward compatibility & Out-of-State Fallback ---

def calculate_grid_bounds(center_lat: float, center_lon: float, width_m: float, height_m: float) -> tuple[float, float, float, float]:
    R = 6378137.0
    d_lat_rad = (height_m / 2.0) / R
    d_lon_rad = (width_m / 2.0) / (R * math.cos(math.radians(center_lat)))
    d_lat = math.degrees(d_lat_rad)
    d_lon = math.degrees(d_lon_rad)
    return (center_lat - d_lat, center_lat + d_lat, center_lon - d_lon, center_lon + d_lon)

def fetch_point_elevation(lat: float, lon: float, attempt: int = 1, max_retries: int = 3) -> float:
    params = {"x": lon, "y": lat, "wkid": 4326, "units": "Meters", "includeDate": "false"}
    try:
        response = requests.get(USGS_URL, params=params, timeout=8)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and "value" in data:
                try:
                    return float(data["value"])
                except (ValueError, TypeError):
                    pass
            raise ValueError(f"Invalid USGS response: {data}")
        response.raise_for_status()
    except (requests.RequestException, ValueError, KeyError):
        if attempt < max_retries:
            import time
            time.sleep(0.5 * attempt)
            return fetch_point_elevation(lat, lon, attempt + 1, max_retries)
        return float('nan')

def get_elevation_grid(center_lat: float, center_lon: float, width_m: float, height_m: float, resolution: int = 30, max_workers: int = 20) -> tuple[np.ndarray, float, float]:
    if resolution < 3:
        raise ValueError("Resolution must be at least 3.")
    south, north, west, east = calculate_grid_bounds(center_lat, center_lon, width_m, height_m)
    lats = np.linspace(south, north, resolution)
    lons = np.linspace(west, east, resolution)
    elevations = np.zeros((resolution, resolution))
    tasks = {(r, c): (lats[r], lons[c]) for r in range(resolution) for c in range(resolution)}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {executor.submit(fetch_point_elevation, lat, lon): (r, c) for (r, c), (lat, lon) in tasks.items()}
        for future in as_completed(future_to_index):
            r, c = future_to_index[future]
            try:
                elevations[r, c] = future.result()
            except Exception:
                elevations[r, c] = float('nan')
    nan_mask = np.isnan(elevations)
    if nan_mask.any():
        for r in range(resolution):
            for c in range(resolution):
                if np.isnan(elevations[r, c]):
                    neighbors = []
                    for dr in [-1, 0, 1]:
                        for dc in [-1, 0, 1]:
                            nr, nc = r + dr, c + dc
                            if 0 <= nr < resolution and 0 <= nc < resolution:
                                val = elevations[nr, nc]
                                if not np.isnan(val):
                                    neighbors.append(val)
                    elevations[r, c] = sum(neighbors) / len(neighbors) if neighbors else 0.0
    if np.isnan(elevations).any():
        elevations = np.nan_to_num(elevations, nan=0.0)
    dx_m = width_m / (resolution - 1)
    dy_m = height_m / (resolution - 1)
    return elevations, dx_m, dy_m
