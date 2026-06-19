import sys
import os
import argparse
import math
import json
import time
import asyncio
import numpy as np
from shapely.geometry import shape, Polygon as ShapelyPolygon

# Include current directory in path to resolve local imports cleanly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tools.geocoder import geocode_address
from tools.dem_downloader import get_elevation_grid, calculate_grid_bounds, DEMDownloader
from tools.mesh_builder import build_solid_mesh, ManifoldMeshBuilder
from tools.stl_writer import write_binary_stl
from harness.validator import validate_mesh, MeshValidator
from visualizer import create_plotly_visual
from tools.parcel_service import query_ct_parcel
from harness.policy_server import PolicyService
from tools.context_resolver import resolve_context

def log_trajectory(log_file: str, step: str, details: dict, status: str = "success") -> None:
    """Appends a step in the Vibe Trajectory observability log (JSONLines format)."""
    log_entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "step": step,
        "details": details,
        "status": status
    }
    with open(log_file, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

def run_pipeline(
    address_or_coords: str,
    width_m: float,
    height_m: float,
    resolution: int,
    model_width_mm: float,
    base_thickness_mm: float,
    z_exaggeration: float,
    output_stl: str,
    output_html: str,
    clip_to_parcel: bool = True,
    role: str = "viewer",
    env: str = "production"
) -> bool:
    """Orchestrates the address-to-STL pipeline supporting exact-parcel LiDAR triangulation."""
    log_file = "vibe_trajectory.jsonl"
    
    # Reset trajectory log
    if os.path.exists(log_file):
        try:
            os.remove(log_file)
        except OSError:
            pass
        
    print("=" * 60)
    print(" TOPO-TWIN AGENT: 3D PROPERTY TOPOLOGY GENERATOR")
    print("=" * 60)
    
    log_trajectory(log_file, "pipeline_start", {
        "address_or_coords": address_or_coords,
        "width_m": width_m,
        "height_m": height_m,
        "resolution": resolution,
        "role": role,
        "env": env
    })

    # Initialize Policy Server (Harness)
    policy = PolicyService(role=role, env=env)

    # 1. Geocode Address - Check Gating First
    if not policy.is_tool_allowed("geocode_address"):
        log_trajectory(log_file, "geocoding", {"error": "Policy Check Blocked"}, "blocked")
        return False

    try:
        is_direct_coords = False
        if "," in address_or_coords:
            parts = address_or_coords.split(",")
            if len(parts) == 2:
                try:
                    lat = float(parts[0].strip())
                    lon = float(parts[1].strip())
                    is_direct_coords = True
                    location_name = f"Coordinates: {lat}, {lon}"
                    print(f"Using direct coordinates: {lat}, {lon}")
                except ValueError:
                    pass
        
        if not is_direct_coords:
            print(f"Geocoding address: '{address_or_coords}'...")
            lat, lon, location_name = geocode_address(address_or_coords)
            print(f"Resolved Location: {location_name}")
            print(f"Coordinates: Lat {lat:.5f}, Lon {lon:.5f}")
            
        log_trajectory(log_file, "geocoding", {
            "resolved_name": location_name,
            "lat": lat,
            "lon": lon
        })
    except Exception as e:
        print(f"ERROR resolving location: {e}", file=sys.stderr)
        log_trajectory(log_file, "geocoding", {"error": str(e)}, "failed")
        return False

    # 2. Query Parcel Service - Check Gating First
    if not policy.is_tool_allowed("query_ct_parcel"):
        log_trajectory(log_file, "parcel_query", {"error": "Policy Check Blocked"}, "blocked")
        return False

    # Semantic check for coordinates
    if not policy.check_action_semantic("query_ct_parcel", {"lat": lat, "lon": lon}):
        log_trajectory(log_file, "parcel_query", {"error": "Semantic Gating Blocked"}, "blocked")
        return False

    parcel_info = None
    geometry_geojson = None
    if clip_to_parcel:
        print("\n[Step 0/4] Querying parcel boundaries for property...")
        parcel_info = query_ct_parcel(lat, lon)
        if parcel_info:
            geometry_geojson = parcel_info["geometry"]
            print("  Parcel found!")
            print(f"  Town: {parcel_info['town']}")
            print(f"  Owner: {parcel_info['owner']}")
            print(f"  Address: {parcel_info['address']}")
            print(f"  Geometry Type: {geometry_geojson.get('type')}")
            log_trajectory(log_file, "parcel_query", {
                "parcel_found": True,
                "town": parcel_info["town"],
                "geometry_type": geometry_geojson.get("type")
            })
        else:
            print("  No parcel boundary found (or coordinates outside Connecticut).")
            print("  Falling back to standard rectangular bounding box.")
            log_trajectory(log_file, "parcel_query", {"parcel_found": False})

    # 3. Fetch Elevation Data
    if not policy.is_tool_allowed("get_elevation_grid"):
        log_trajectory(log_file, "get_elevation_grid", {"error": "Policy Check Blocked"}, "blocked")
        return False
        
    if not policy.check_action_semantic("get_elevation_grid", {"center_lat": lat, "center_lon": lon}):
        log_trajectory(log_file, "get_elevation_grid", {"error": "Semantic Gating Blocked"}, "blocked")
        return False

    # Check if we have exact parcel geometry inside CT
    if geometry_geojson:
        print("\n[Step 1/4] Fetching high-resolution CT ECO 2023 LiDAR elevation data...")
        try:
            poly_shape = shape(geometry_geojson)
            min_x, min_y, max_x, max_y = poly_shape.bounds
            width_ft = max_x - min_x
            
            # Determine appropriate grid resolution spacing in feet
            resolution_feet = width_ft / resolution
            
            downloader = DEMDownloader(max_concurrency=5)
            # Generate coordinate grid in EPSG:6434 feet
            grid_points = downloader.generate_parcel_grid(poly_shape.bounds, resolution_feet=resolution_feet)
            
            # Filter grid points to keep only those strictly inside the parcel
            from shapely import contains_xy
            inside_mask = contains_xy(poly_shape, grid_points[:, 0], grid_points[:, 1])
            interior_pts = grid_points[inside_mask]
            
            # Extract boundary vertices
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
            
            # Combine boundary and interior points
            combined_pts = np.vstack((boundary_pts, interior_pts))
            
            # Remove duplicate coordinates (within 0.001 feet tolerance)
            _, unique_idx = np.unique(np.round(combined_pts, 3), axis=0, return_index=True)
            points_2d_ft = combined_pts[unique_idx]
            
            # Fetch elevations concurrently (returns elevations in feet)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            grid_elevations_ft = loop.run_until_complete(downloader.download_elevations(points_2d_ft))
            loop.close()
            
            # Extract planar coordinates and convert elevations to meters
            points_2d = grid_elevations_ft[:, :2]
            elevations_m = grid_elevations_ft[:, 2] * 0.3048
            
            print(f"Fetched {len(points_2d)} elevation points concurrently.")
            print(f"Elevation stats: Min={np.min(elevations_m):.2f}m, Max={np.max(elevations_m):.2f}m, Range={np.max(elevations_m)-np.min(elevations_m):.2f}m")
            
            log_trajectory(log_file, "get_elevation_grid", {
                "source": "UConn CT ECO 2023 2-Foot LiDAR ImageServer",
                "points_count": len(points_2d),
                "min_elevation": float(np.min(elevations_m)),
                "max_elevation": float(np.max(elevations_m))
            })
        except Exception as e:
            print(f"ERROR downloading elevation data from UConn ImageServer: {e}", file=sys.stderr)
            log_trajectory(log_file, "get_elevation_grid", {"error": str(e)}, "failed")
            return False
    else:
        # Fallback to USGS EPQS for rectangular coordinates / out-of-state
        print("\n[Step 1/4] Fetching elevation data from USGS...")
        try:
            elevations, dx_m, dy_m = get_elevation_grid(
                center_lat=lat,
                center_lon=lon,
                width_m=width_m,
                height_m=height_m,
                resolution=resolution
            )
            print(f"Fetched {resolution}x{resolution} grid from USGS EPQS. Cell size: dx={dx_m:.2f}m, dy={dy_m:.2f}m")
            log_trajectory(log_file, "get_elevation_grid", {
                "source": "USGS EPQS",
                "resolution": resolution,
                "min_elevation": float(np.min(elevations)),
                "max_elevation": float(np.max(elevations))
            })
        except Exception as e:
            print(f"ERROR downloading elevation data from USGS: {e}", file=sys.stderr)
            log_trajectory(log_file, "get_elevation_grid", {"error": str(e)}, "failed")
            return False

    # 4. Construct 3D mesh
    if not policy.is_tool_allowed("build_solid_mesh"):
        log_trajectory(log_file, "build_solid_mesh", {"error": "Policy Check Blocked"}, "blocked")
        return False

    print("\n[Step 2/4] Constructing solid 3D mesh...")
    attempt = 1
    max_repair_attempts = 3
    validated = False
    
    # Calculate scale factor for base thickness mapping
    if geometry_geojson:
        poly_shape = shape(geometry_geojson)
        min_x, min_y, max_x, max_y = poly_shape.bounds
        width_ft = max_x - min_x
        model_scale = model_width_mm / (width_ft * 0.3048)
    else:
        model_scale = model_width_mm / (width_m)
        
    while attempt <= max_repair_attempts:
        try:
            if geometry_geojson:
                # Convert the requested base thickness in model mm to real world meters
                thickness_meters = base_thickness_mm / (model_scale * z_exaggeration)
                
                builder = ManifoldMeshBuilder(geometry_geojson, thickness_meters=thickness_meters)
                vertices, faces = builder.build_mesh(
                    points_2d=points_2d,
                    elevations_m=elevations_m,
                    model_width_mm=model_width_mm,
                    z_exaggeration=z_exaggeration
                )
                print(f"Constructed exact-parcel mesh with {len(faces)} faces.")
                log_trajectory(log_file, "build_solid_mesh", {"attempt": attempt, "faces_count": len(faces)})
            else:
                # Fallback build_solid_mesh returning triangles
                south, north, west, east = calculate_grid_bounds(lat, lon, width_m, height_m)
                lats = np.linspace(south, north, resolution)
                lons = np.linspace(west, east, resolution)
                triangles = build_solid_mesh(
                    elevations=elevations,
                    dx_m=dx_m,
                    dy_m=dy_m,
                    model_width_mm=model_width_mm,
                    base_thickness_mm=base_thickness_mm,
                    z_exaggeration=z_exaggeration,
                    lats=lats,
                    lons=lons,
                    polygon=None
                )
                
                # Convert triangles to vertices/faces arrays for uniform Trimesh validation
                unique_verts = []
                unique_verts_map = {}
                faces = []
                for tri in triangles:
                    face_idx = []
                    for v in tri:
                        v_rounded = (round(v[0], 5), round(v[1], 5), round(v[2], 5))
                        if v_rounded not in unique_verts_map:
                            unique_verts_map[v_rounded] = len(unique_verts)
                            unique_verts.append(v)
                        face_idx.append(unique_verts_map[v_rounded])
                    faces.append(face_idx)
                vertices = np.array(unique_verts, dtype=np.float32)
                faces = np.array(faces, dtype=np.int32)
                
                print(f"Constructed fallback rectangular mesh with {len(faces)} faces.")
                log_trajectory(log_file, "build_solid_mesh", {"attempt": attempt, "faces_count": len(faces)})
        except Exception as e:
            print(f"ERROR building mesh: {e}", file=sys.stderr)
            log_trajectory(log_file, "build_solid_mesh", {"error": str(e)}, "failed")
            return False

        # 5. Run Validation Harness & Green Team Self-Repair
        if not policy.is_tool_allowed("validate_mesh"):
            log_trajectory(log_file, "validate_mesh", {"error": "Policy Check Blocked"}, "blocked")
            return False

        print(f"\n[Step 3/4] Running geometric validation harness (Attempt {attempt})...")
        validation = validate_mesh(vertices, faces)
        print(f"  Watertight (Manifold): {validation['watertight']}")
        print(f"  Volume: {validation['volume']:.2f} cubic mm")
        
        log_trajectory(log_file, "validate_mesh", {
            "attempt": attempt,
            "valid": validation["valid"],
            "watertight": validation["watertight"],
            "volume": validation["volume"],
            "errors": validation["errors"]
        })
        
        if validation["valid"]:
            print("Validation passed! Mesh is watertight and clean.")
            validated = True
            break
        else:
            print(f"[GREEN TEAM - ANOMALY DETECTED] Mesh failed validation (Attempt {attempt})!", file=sys.stderr)
            for err in validation["errors"]:
                print(f"  - {err}", file=sys.stderr)
                
            if attempt < max_repair_attempts:
                print("[GREEN TEAM - AUTO-REPAIR] Executing self-repair: modifying base thickness and rebuilding...", file=sys.stderr)
                base_thickness_mm += 1.0  # Safe recovery: increase thickness to force positive volume
                attempt += 1
            else:
                print("[GREEN TEAM - FAIL] Self-repair attempts exhausted. Aborting.", file=sys.stderr)
                return False

    if not validated:
        return False

    # 6. Export STL and HTML - Check Gating First
    if not (policy.is_tool_allowed("write_binary_stl") and policy.is_tool_allowed("create_plotly_visual")):
        log_trajectory(log_file, "export_files", {"error": "Policy Check Blocked"}, "blocked")
        return False

    print("\n[Step 4/4] Writing output files...")
    try:
        # Convert vertices and faces to triangles for legacy write_binary_stl/visualizer compatibility
        triangles = [
            (tuple(vertices[face[0]]), tuple(vertices[face[1]]), tuple(vertices[face[2]]))
            for face in faces
        ]
        
        write_binary_stl(output_stl, triangles)
        
        # Build 3D polygon outline in model coordinates for visualizer
        polygon_coords_model = None
        if geometry_geojson:
            polygon_coords_model = []
            poly_shape = shape(geometry_geojson)
            
            # Determine min coordinates in model coordinates (after selective shift)
            X_scaled_all = (points_2d[:, 0] * 0.3048) * model_scale
            Y_scaled_all = (points_2d[:, 1] * 0.3048) * model_scale
            min_x_scaled = np.min(X_scaled_all)
            min_y_scaled = np.min(Y_scaled_all)
            
            # Gather all rings (exteriors and interiors of all parts)
            rings = []
            if isinstance(poly_shape, ShapelyPolygon):
                rings.append(list(poly_shape.exterior.coords))
                for hole in poly_shape.interiors:
                    rings.append(list(hole.coords))
            elif isinstance(poly_shape, ShapelyMultiPolygon):
                for sub_poly in poly_shape.geoms:
                    rings.append(list(sub_poly.exterior.coords))
                    for hole in sub_poly.interiors:
                        rings.append(list(hole.coords))
            
            # Build list of points in model coordinates, separating rings with None values
            first_ring = True
            for ring in rings:
                if not first_ring:
                    polygon_coords_model.append((None, None, None))
                first_ring = False
                
                for pt in ring:
                    x_ft, y_ft = pt[0], pt[1]
                    x_m = x_ft * 0.3048
                    y_m = y_ft * 0.3048
                    
                    # Scale to model mm
                    x_mm = x_m * model_scale
                    y_mm = y_m * model_scale
                    
                    # Find the nearest point in points_2d to get its Z coordinate
                    dists = np.hypot(points_2d[:, 0] - x_ft, points_2d[:, 1] - y_ft)
                    nearest_idx = np.argmin(dists)
                    z_mm = elevations_m[nearest_idx] * z_exaggeration * model_scale
                    
                    # Apply origin shift
                    x_mm -= min_x_scaled
                    y_mm -= min_y_scaled
                    
                    polygon_coords_model.append((x_mm, y_mm, z_mm + 0.5))
        
        # Write HTML
        title = f"TopoTwin: {address_or_coords}"
        if parcel_info:
            title += f" (Clipped to Parcel, {parcel_info['town']})"
        else:
            title += f" ({width_m:.0f}m x {height_m:.0f}m)"
            
        create_plotly_visual(
            triangles=triangles, 
            output_html=output_html, 
            title=title, 
            polygon_coords=polygon_coords_model
        )
        
        print("\n" + "=" * 60)
        print(" SUCCESS! Pipeline completed.")
        print(f"  Output STL: {os.path.abspath(output_stl)}")
        print(f"  Output HTML: {os.path.abspath(output_html)}")
        print("=" * 60)
        
        log_trajectory(log_file, "export_files", {
            "stl_path": output_stl,
            "html_path": output_html
        })
        return True
    except Exception as e:
        print(f"ERROR saving outputs: {e}", file=sys.stderr)
        log_trajectory(log_file, "export_files", {"error": str(e)}, "failed")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate 3D-printable terrain models from address/coordinates.")
    parser.add_argument("address", help="Address or comma-separated 'lat,lon' coordinates")
    parser.add_argument("--width", type=float, default=200.0, help="Bounding box width in meters (default: 200)")
    parser.add_argument("--height", type=float, default=200.0, help="Bounding box height in meters (default: 200)")
    parser.add_argument("--resolution", type=int, default=40, help="Grid resolution NxN (default: 40)")
    parser.add_argument("--model-width", type=float, default=100.0, help="Output physical model width in mm (default: 100)")
    parser.add_argument("--base-thickness", type=float, default=2.0, help="Base thickness in mm (default: 2)")
    parser.add_argument("--z-exaggeration", type=float, default=2.0, help="Vertical exaggeration scale (default: 2.0)")
    parser.add_argument("--output-stl", default="terrain.stl", help="Output STL filename (default: terrain.stl)")
    parser.add_argument("--output-html", default="terrain.html", help="Output HTML visualization filename (default: terrain.html)")
    parser.add_argument("--no-clip", dest="clip_to_parcel", action="store_false", help="Disable parcel-boundary clipping")
    
    # Adding role and environment parameters for Gating check demo
    parser.add_argument("--role", default="viewer", choices=["viewer", "admin"], help="Security role to run the agent under")
    parser.add_argument("--env", default="production", choices=["localhost", "production"], help="Security environment to run the agent under")
    
    args = parser.parse_args()
    
    success = run_pipeline(
        address_or_coords=args.address,
        width_m=args.width,
        height_m=args.height,
        resolution=args.resolution,
        model_width_mm=args.model_width,
        base_thickness_mm=args.base_thickness,
        z_exaggeration=args.z_exaggeration,
        output_stl=args.output_stl,
        output_html=args.output_html,
        clip_to_parcel=args.clip_to_parcel,
        role=args.role,
        env=args.env
    )
    
    sys.exit(0 if success else 1)
