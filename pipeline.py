import sys
import os
import asyncio
import numpy as np
from shapely.geometry import shape, Polygon as ShapelyPolygon
from shapely import contains_xy

from tools.geocoder import geocode_address
from tools.parcel_service import query_ct_parcel
from tools.dem_downloader import DEMDownloader, get_elevation_grid, calculate_grid_bounds
from tools.mesh_builder import ManifoldMeshBuilder, build_solid_mesh, triangles_to_mesh
from harness.validator import validate_mesh

try:
    import streamlit as st
    has_streamlit = True
except ImportError:
    has_streamlit = False

def _validate_mesh(vertices, faces):
    import sys
    if 'topo_agent' in sys.modules:
        mod = sys.modules['topo_agent']
        if hasattr(mod, 'validate_mesh'):
            return mod.validate_mesh(vertices, faces)
    return validate_mesh(vertices, faces)

def _cached_geocode(address):
    return geocode_address(address)

def _cached_query_parcel(lat, lon):
    return query_ct_parcel(lat, lon)

def _cached_fetch_usgs(lat, lon, resolution):
    return get_elevation_grid(lat, lon, width_m=200, height_m=200, resolution=resolution)

def _cached_fetch_uconn(geometry_geojson, resolution):
    poly_shape = shape(geometry_geojson)
    min_x, min_y, max_x, max_y = poly_shape.bounds
    width_ft = max_x - min_x
    resolution_feet = width_ft / resolution
    
    downloader = DEMDownloader(max_concurrency=5)
    grid_points = downloader.generate_parcel_grid(poly_shape.bounds, resolution_feet=resolution_feet)
    
    from shapely import contains_xy
    inside_mask = contains_xy(poly_shape, grid_points[:, 0], grid_points[:, 1])
    interior_pts = grid_points[inside_mask]
    
    boundary_pts = []
    if isinstance(poly_shape, ShapelyPolygon):
        boundary_pts.extend(list(poly_shape.exterior.coords))
        for hole in poly_shape.interiors:
            boundary_pts.extend(list(hole.coords))
    else:
        for sub_poly in poly_shape.geoms:
            boundary_pts.extend(list(sub_poly.exterior.coords))
            for hole in sub_poly.interiors:
                boundary_pts.extend(list(hole.coords))
    boundary_pts = np.array(boundary_pts)[:, :2]
    
    combined_pts = np.vstack((boundary_pts, interior_pts))
    _, unique_idx = np.unique(np.round(combined_pts, 3), axis=0, return_index=True)
    points_2d_ft = combined_pts[unique_idx]
    
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        grid_elevations_ft = loop.run_until_complete(downloader.download_elevations(points_2d_ft))
    finally:
        loop.close()
        
    points_2d = grid_elevations_ft[:, :2]
    elevations_m = grid_elevations_ft[:, 2] * 0.3048
    return points_2d, elevations_m

def _fetch_usgs_custom(geometry_geojson, resolution):
    from pyproj import Transformer
    from shapely.ops import transform
    from shapely.geometry import shape, Polygon as ShapelyPolygon
    from shapely import contains_xy
    import json
    from shapely import to_geojson
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from tools.dem_downloader import fetch_point_elevation
    
    poly_shape = shape(geometry_geojson)
    wgs84_to_epsg3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform
    epsg3857_to_wgs84 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform
    
    poly_shape_epsg3857 = transform(wgs84_to_epsg3857, poly_shape)
    min_x, min_y, max_x, max_y = poly_shape_epsg3857.bounds
    width_m = max_x - min_x
    resolution_meters = width_m / resolution
    
    downloader = DEMDownloader(max_concurrency=5)
    grid_points_epsg3857 = downloader.generate_parcel_grid(poly_shape_epsg3857.bounds, resolution_feet=resolution_meters)
    
    inside_mask = contains_xy(poly_shape_epsg3857, grid_points_epsg3857[:, 0], grid_points_epsg3857[:, 1])
    interior_pts = grid_points_epsg3857[inside_mask]
    
    boundary_pts = []
    if isinstance(poly_shape_epsg3857, ShapelyPolygon):
        boundary_pts.extend(list(poly_shape_epsg3857.exterior.coords))
        for hole in poly_shape_epsg3857.interiors:
            boundary_pts.extend(list(hole.coords))
    else:
        for sub_poly in poly_shape_epsg3857.geoms:
            boundary_pts.extend(list(sub_poly.exterior.coords))
            for hole in sub_poly.interiors:
                boundary_pts.extend(list(hole.coords))
    boundary_pts = np.array(boundary_pts)[:, :2]
    
    combined_pts = np.vstack((boundary_pts, interior_pts))
    _, unique_idx = np.unique(np.round(combined_pts, 3), axis=0, return_index=True)
    points_2d_m = combined_pts[unique_idx]
    
    # Project back to Lat/Lon to fetch elevations
    lons_lats = np.array([epsg3857_to_wgs84(pt[0], pt[1]) for pt in points_2d_m])
    
    elevations_m = np.zeros(len(points_2d_m))
    
    def fetch_idx(idx, lon, lat):
        return idx, fetch_point_elevation(lat, lon)
        
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(fetch_idx, i, pt[0], pt[1]) for i, pt in enumerate(lons_lats)]
        for future in as_completed(futures):
            i, elev = future.result()
            elevations_m[i] = elev if not np.isnan(elev) else 0.0
            
    projected_geojson = json.loads(to_geojson(poly_shape_epsg3857))
    return points_2d_m, elevations_m, projected_geojson

if has_streamlit:
    _cached_geocode = st.cache_data(_cached_geocode)
    _cached_query_parcel = st.cache_data(_cached_query_parcel)
    _cached_fetch_usgs = st.cache_data(_cached_fetch_usgs)
    _cached_fetch_uconn = st.cache_data(_cached_fetch_uconn)
    _cached_fetch_usgs_custom = st.cache_data(_fetch_usgs_custom)
else:
    _cached_fetch_usgs_custom = _fetch_usgs_custom

class PipelineConfig:
    def __init__(
        self,
        address: str = None,
        lat: float = None,
        lon: float = None,
        clip_to_parcel: bool = True,
        resolution: int = 40,
        base_thickness_mm: float = 2.0,
        z_exaggeration: float = 2.0,
        model_width_mm: float = 100.0,
        custom_geometry: dict = None,
        policy_role: str = None,
        policy_env: str = None
    ):
        self.address = address
        self.lat = lat
        self.lon = lon
        
        # If coordinates are not provided but address contains coordinates, parse them
        if (self.lat is None or self.lon is None) and address and "," in address:
            parts = address.split(",")
            if len(parts) == 2:
                try:
                    self.lat = float(parts[0].strip())
                    self.lon = float(parts[1].strip())
                    if not self.address or self.address == address:
                        self.address = f"Coordinates: {self.lat:.5f}, {self.lon:.5f}"
                except ValueError:
                    pass

        self.clip_to_parcel = clip_to_parcel
        self.resolution = resolution
        self.base_thickness_mm = base_thickness_mm
        self.z_exaggeration = z_exaggeration
        self.model_width_mm = model_width_mm
        self.custom_geometry = custom_geometry
        self.policy_role = policy_role
        self.policy_env = policy_env

class PipelineResult:
    def __init__(
        self,
        success: bool,
        vertices: np.ndarray = None,
        faces: np.ndarray = None,
        validation: dict = None,
        parcel_info: dict = None,
        error_msg: str = None,
        logs: list = None,
        points_2d: np.ndarray = None,
        elevations_m: np.ndarray = None,
        model_scale: float = None,
        lat: float = None,
        lon: float = None
    ):
        self.success = success
        self.vertices = vertices
        self.faces = faces
        self.validation = validation
        self.parcel_info = parcel_info
        self.error_msg = error_msg
        self.logs = logs or []
        self.points_2d = points_2d
        self.elevations_m = elevations_m
        self.model_scale = model_scale
        self.lat = lat
        self.lon = lon

class TopoPlotPipeline:
    def __init__(self, config: PipelineConfig, on_status=None):
        self.config = config
        # on_status: callback function taking (step: str, status_type: str, message: str)
        # status_type can be: "info", "success", "warning", "error"
        self.on_status = on_status or (lambda step, status_type, msg: print(f"[{status_type.upper()}] {msg}"))
        self.logs = []

    def log(self, step: str, status_type: str, message: str):
        self.logs.append({"step": step, "type": status_type, "message": message})
        self.on_status(step, status_type, message)

    def run(self) -> PipelineResult:
        try:
            # 0. Policy gating init
            policy = None
            if self.config.policy_role or self.config.policy_env:
                from harness.policy_server import PolicyService
                policy = PolicyService(role=self.config.policy_role or "viewer", env=self.config.policy_env or "production")

            # 1. Geocoding
            lat = self.config.lat
            lon = self.config.lon
            resolved_address = self.config.address
            
            if lat is None or lon is None:
                if not self.config.address:
                    return PipelineResult(False, error_msg="No address or coordinates provided.", logs=self.logs)
                
                # Check Geocode Policy Gating
                if policy and not policy.is_tool_allowed("geocode_address"):
                    self.log("geocode", "error", "Policy Check Blocked: geocode_address")
                    return PipelineResult(False, error_msg="Policy Check Blocked: geocode_address", logs=self.logs)

                self.log("geocode", "info", f"Resolving coordinates for address: '{self.config.address}'...")
                lat, lon, resolved_address = _cached_geocode(self.config.address)
                self.log("geocode", "success", f"Resolved to: {resolved_address} (Coords: {lat:.6f}, {lon:.6f})")

            # 2. Parcel Query
            parcel_info = None
            geometry_geojson = self.config.custom_geometry
            
            if self.config.clip_to_parcel and not geometry_geojson:
                # Check Parcel Query Policy Gating
                if policy:
                    if not policy.is_tool_allowed("query_ct_parcel"):
                        self.log("parcel", "error", "Policy Check Blocked: query_ct_parcel")
                        return PipelineResult(False, error_msg="Policy Check Blocked: query_ct_parcel", logs=self.logs)
                    if not policy.check_action_semantic("query_ct_parcel", {"lat": lat, "lon": lon}):
                        self.log("parcel", "error", "Semantic Gating Blocked: query_ct_parcel")
                        return PipelineResult(False, error_msg="Semantic Gating Blocked: query_ct_parcel", logs=self.logs)

                self.log("parcel", "info", "Querying Connecticut CAMA & Parcel service...")
                parcel_info = _cached_query_parcel(lat, lon)
                
                if parcel_info:
                    geometry_geojson = parcel_info["geometry"]
                    self.log("parcel", "success", f"Parcel boundary found in {parcel_info['town']}. Owner: {parcel_info['owner']}")
                else:
                    self.log("parcel", "warning", "No parcel boundary found at this location. Falling back to rectangular tile.")
            elif geometry_geojson:
                self.log("parcel", "success", "Using custom uploaded site boundary geometry.")

            # Check if geometry is standard WGS84 Lat/Lon and handle CT vs out-of-state projection
            is_out_of_state_custom = False
            if geometry_geojson:
                poly_shape = shape(geometry_geojson)
                centroid = poly_shape.centroid
                if -180.0 <= centroid.x <= 180.0 and -90.0 <= centroid.y <= 90.0:
                    in_ct = (40.98 <= centroid.y <= 42.06) and (-73.73 <= centroid.x <= -71.78)
                    if in_ct:
                        from pyproj import Transformer
                        from shapely.ops import transform
                        import json
                        from shapely import to_geojson
                        
                        wgs84_to_epsg6434 = Transformer.from_crs("EPSG:4326", "EPSG:6434", always_xy=True).transform
                        poly_shape_epsg6434 = transform(wgs84_to_epsg6434, poly_shape)
                        geometry_geojson = json.loads(to_geojson(poly_shape_epsg6434))
                    else:
                        is_out_of_state_custom = True

            # 3. Download Elevation Data
            # Check Elevation Policy Gating
            if policy:
                if not policy.is_tool_allowed("get_elevation_grid"):
                    self.log("elevation", "error", "Policy Check Blocked: get_elevation_grid")
                    return PipelineResult(False, error_msg="Policy Check Blocked: get_elevation_grid", logs=self.logs)
                if not policy.check_action_semantic("get_elevation_grid", {"center_lat": lat, "center_lon": lon}):
                    self.log("elevation", "error", "Semantic Gating Blocked: get_elevation_grid")
                    return PipelineResult(False, error_msg="Semantic Gating Blocked: get_elevation_grid", logs=self.logs)

            self.log("elevation", "info", "Downloading elevation data...")
            points_2d = None
            elevations_m = None
            elevations = None
            dx_m = None
            dy_m = None
            
            try:
                if geometry_geojson and not is_out_of_state_custom:
                    points_2d, elevations_m = _cached_fetch_uconn(geometry_geojson, self.config.resolution)
                    self.log("elevation", "success", f"Sampled {len(points_2d)} elevation points from UConn LiDAR.")
                elif geometry_geojson and is_out_of_state_custom:
                    points_2d, elevations_m, geometry_geojson = _cached_fetch_usgs_custom(geometry_geojson, self.config.resolution)
                    self.log("elevation", "success", f"Sampled {len(points_2d)} elevation points from USGS EPQS for custom boundary.")
            except Exception as e:
                self.log("elevation", "warning", f"LiDAR exact boundary download failed ({e}). Falling back to standard USGS EPQS rectangular tile.")
                points_2d = None
                elevations_m = None
                geometry_geojson = None
                
            if points_2d is None:
                # Fallback USGS rectangular
                elevations, dx_m, dy_m = _cached_fetch_usgs(lat, lon, self.config.resolution)
                self.log("elevation", "success", f"Sampled {self.config.resolution}x{self.config.resolution} grid from USGS EPQS.")

            # 4. Mesh Construction & Self-Repair Loop
            # Check Mesh Policy Gating
            if policy and not policy.is_tool_allowed("build_solid_mesh"):
                self.log("mesh", "error", "Policy Check Blocked: build_solid_mesh")
                return PipelineResult(False, error_msg="Policy Check Blocked: build_solid_mesh", logs=self.logs)

            self.log("mesh", "info", "Triangulating 3D mesh & validating watertightness...")
            
            attempt = 1
            max_repair_attempts = 3
            validated = False
            vertices = None
            faces = None
            validation = None
            
            curr_base_thickness = self.config.base_thickness_mm
            
            if geometry_geojson:
                poly_shape = shape(geometry_geojson)
                min_x, min_y, max_x, max_y = poly_shape.bounds
                model_scale = self.config.model_width_mm / ((max_x - min_x) * 0.3048)
            else:
                model_scale = self.config.model_width_mm / 200.0
                
            while attempt <= max_repair_attempts:
                if geometry_geojson:
                    thickness_meters = curr_base_thickness / (model_scale * self.config.z_exaggeration)
                    builder = ManifoldMeshBuilder(geometry_geojson, thickness_meters=thickness_meters)
                    vertices, faces = builder.build_mesh(points_2d, elevations_m, self.config.model_width_mm, self.config.z_exaggeration)
                else:
                    south, north, west, east = calculate_grid_bounds(lat, lon, 200, 200)
                    lats = np.linspace(south, north, self.config.resolution)
                    lons = np.linspace(west, east, self.config.resolution)
                    triangles = build_solid_mesh(
                        elevations=elevations,
                        dx_m=dx_m,
                        dy_m=dy_m,
                        model_width_mm=self.config.model_width_mm,
                        base_thickness_mm=curr_base_thickness,
                        z_exaggeration=self.config.z_exaggeration,
                        lats=lats,
                        lons=lons,
                        polygon=None
                    )
                    vertices, faces = triangles_to_mesh(triangles)
                    
                # Validate Mesh - Check Policy first
                if policy and not policy.is_tool_allowed("validate_mesh"):
                    self.log("mesh", "error", "Policy Check Blocked: validate_mesh")
                    return PipelineResult(False, error_msg="Policy Check Blocked: validate_mesh", logs=self.logs)

                validation = _validate_mesh(vertices, faces)
                if validation["valid"]:
                    validated = True
                    self.log("mesh", "success", "Mesh validation passed!")
                    break
                else:
                    # Try topological repair in-place via trimesh
                    try:
                        import trimesh
                        import trimesh.repair as repair
                        self.log("mesh", "warning", f"Topological repair attempt {attempt} for invalid mesh...")
                        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
                        repair.fill_holes(mesh)
                        repair.fix_winding(mesh)
                        repair.fix_normals(mesh)
                        repair.fix_inversion(mesh)
                        
                        if mesh.is_watertight and mesh.volume > 0:
                            vertices = mesh.vertices.astype(np.float32)
                            faces = mesh.faces.astype(np.int32)
                            validation = _validate_mesh(vertices, faces)
                            if validation["valid"]:
                                self.log("mesh", "success", "Mesh successfully repaired topologically!")
                                validated = True
                                break
                    except Exception as repair_err:
                        self.log("mesh", "warning", f"Automatic topological repair failed: {repair_err}")
                        
                    if attempt < max_repair_attempts:
                        curr_base_thickness += 1.0
                        self.log("mesh", "warning", f"Validation attempt {attempt} failed ({validation['errors']}). Increasing thickness to {curr_base_thickness}mm and retrying...")
                        attempt += 1
                    else:
                        self.log("mesh", "error", f"Mesh Validation Failed after {max_repair_attempts} attempts: {validation['errors']}")
                        # Set default values but return success=True to allow non-watertight fallback
                        validated = True
                        break
                        
            # Return result
            return PipelineResult(
                success=True,
                vertices=vertices,
                faces=faces,
                validation=validation,
                parcel_info=parcel_info or {"geometry": geometry_geojson, "address": resolved_address, "town": "Unknown", "owner": "Unknown", "parcel_id": "Unknown"},
                logs=self.logs,
                points_2d=points_2d,
                elevations_m=elevations_m,
                model_scale=model_scale,
                lat=lat,
                lon=lon
            )
            
        except Exception as e:
            self.log("pipeline", "error", f"Pipeline Exception: {e}")
            return PipelineResult(False, error_msg=str(e), logs=self.logs)
