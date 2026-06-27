import sys
import os
import argparse
import math
import json
import time
import asyncio
import numpy as np
from shapely.geometry import shape, Polygon as ShapelyPolygon, MultiPolygon as ShapelyMultiPolygon



from tools.geocoder import geocode_address
from tools.dem_downloader import get_elevation_grid, calculate_grid_bounds, DEMDownloader
from tools.mesh_builder import build_solid_mesh, ManifoldMeshBuilder, mesh_to_triangles
from tools.stl_writer import write_binary_stl
from harness.validator import validate_mesh, MeshValidator
from visualizer import create_plotly_visual
from tools.parcel_service import query_ct_parcel
from harness.policy_server import PolicyService
from tools.context_resolver import resolve_context
from pipeline import TopoPlotPipeline, PipelineConfig

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

    # Export STL and HTML - Check Gating First
    if not (policy.is_tool_allowed("write_binary_stl") and policy.is_tool_allowed("create_plotly_visual")):
        log_trajectory(log_file, "export_files", {"error": "Policy Check Blocked"}, "blocked")
        return False

    # Setup the pipeline config (coordinate parsing and gating checks are delegated dynamically)
    config = PipelineConfig(
        address=address_or_coords,
        clip_to_parcel=clip_to_parcel,
        resolution=resolution,
        base_thickness_mm=base_thickness_mm,
        z_exaggeration=z_exaggeration,
        model_width_mm=model_width_mm,
        policy_role=role,
        policy_env=env
    )

    def on_status(step, status_type, message):
        # Print status updates to console
        if status_type == "info":
            print(f"\n[Step] {message}")
        elif status_type == "success":
            print(f"  [PASS] {message}")
        elif status_type == "warning":
            print(f"  [WARN] {message}")
        elif status_type == "error":
            print(f"  [FAIL] {message}")
        
        # Log to vibe trajectory
        status = "success"
        if status_type == "error":
            status = "blocked" if ("Blocked" in message or "Gating" in message) else "failed"
        
        if step == "geocode":
            log_trajectory(log_file, "geocoding", {"message": message}, status)
        elif step == "parcel":
            log_trajectory(log_file, "parcel_query", {"message": message}, status)
        elif step == "elevation":
            log_trajectory(log_file, "get_elevation_grid", {"message": message}, status)
        elif step == "mesh":
            step_name = "build_solid_mesh" if "Triangulating" in message or "Constructed" in message else "validate_mesh"
            log_trajectory(log_file, step_name, {"message": message}, status)

    pipeline = TopoPlotPipeline(config, on_status=on_status)
    result = pipeline.run()

    if not result.success:
        print(f"ERROR executing pipeline: {result.error_msg}", file=sys.stderr)
        status_name = "blocked" if ("Blocked" in result.error_msg or "Gating" in result.error_msg) else "failed"
        log_trajectory(log_file, "pipeline_run", {"error": result.error_msg}, status_name)
        return False

    vertices = result.vertices
    faces = result.faces
    parcel_info = result.parcel_info
    points_2d = result.points_2d
    elevations_m = result.elevations_m
    model_scale = result.model_scale
    geometry_geojson = parcel_info.get("geometry") if parcel_info else None

    # Write output files
    print("\n[Step 4/4] Writing output files...")
    try:
        triangles = mesh_to_triangles(vertices, faces)
        write_binary_stl(output_stl, triangles)
        
        # Build 3D polygon outline in model coordinates for visualizer using shared utility
        polygon_coords_model = None
        if geometry_geojson and points_2d is not None and elevations_m is not None:
            from tools.geometry_utils import build_polygon_outline_model_coords
            polygon_coords_model = build_polygon_outline_model_coords(
                geometry_geojson, points_2d, elevations_m, model_scale, z_exaggeration
            )
        
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
