import sys
import os
import time
import numpy as np
import trimesh

# Resolve local imports relative to Kaggle5Day root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.dem_downloader import get_elevation_grid
from tools.mesh_builder import build_solid_mesh
from harness.validator import validate_mesh
from tools.stl_writer import write_binary_stl

BENCHMARKS = [
    {
        "name": "Clinton, CT (Coastal Flat/Hill)",
        "lat": 41.2781,
        "lon": -72.5273,
        "width_m": 200,
        "height_m": 200
    },
    {
        "name": "Grand Canyon, AZ (Deep Ravines)",
        "lat": 36.0544,
        "lon": -112.1401,
        "width_m": 400,
        "height_m": 400
    },
    {
        "name": "Mount Rainier, WA (Steep Peak)",
        "lat": 46.8523,
        "lon": -121.7603,
        "width_m": 500,
        "height_m": 500
    }
]

def run_evaluation_suite(resolution: int = 20) -> bool:
    """Runs end-to-end mesh building and validation checks across multiple benchmark regions."""
    print("=" * 80)
    print("RUNNING AGENTIC HARNESS: TOPO-TWIN EVALUATION SUITE")
    print("=" * 80)
    
    all_passed = True
    summaries = []
    
    for benchmark in BENCHMARKS:
        print(f"\nEvaluating: {benchmark['name']}...")
        print(f"  Query region: {benchmark['width_m']}m x {benchmark['height_m']}m at {benchmark['lat']:.4f}, {benchmark['lon']:.4f}")
        
        start_time = time.time()
        
        # 1. Fetch Elevation Data
        try:
            elevations, dx_m, dy_m = get_elevation_grid(
                center_lat=benchmark['lat'],
                center_lon=benchmark['lon'],
                width_m=benchmark['width_m'],
                height_m=benchmark['height_m'],
                resolution=resolution
            )
            download_time = time.time() - start_time
        except Exception as e:
            print(f"  [FAIL] Download Error: {e}")
            all_passed = False
            summaries.append({
                "name": benchmark["name"],
                "status": "FAIL (Download Error)",
                "time": 0,
                "triangles": 0,
                "watertight": False
            })
            continue

        # 2. Build Mesh
        try:
            mesh_start = time.time()
            triangles = build_solid_mesh(
                elevations=elevations,
                dx_m=dx_m,
                dy_m=dy_m,
                model_width_mm=100.0,
                base_thickness_mm=2.0,
                z_exaggeration=2.5
            )
            mesh_time = time.time() - mesh_start
        except Exception as e:
            print(f"  [FAIL] Mesh Construction Error: {e}")
            all_passed = False
            summaries.append({
                "name": benchmark["name"],
                "status": "FAIL (Mesh Construction Error)",
                "time": download_time,
                "triangles": 0,
                "watertight": False
            })
            continue

        # 3. Validate Mesh
        # Convert triangles list to vertices/faces arrays for the new validate_mesh signature
        try:
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
            
            validation = validate_mesh(vertices, faces)
            total_time = time.time() - start_time
            
            if validation["valid"]:
                print(f"  [PASS] Successfully verified watertight mesh of {len(triangles)} triangles in {total_time:.2f}s. Volume: {validation['volume']:.2f}")
                status = "PASS"
            else:
                print(f"  [FAIL] Mesh failed validation harness!")
                for err in validation["errors"]:
                    print(f"    - {err}")
                all_passed = False
                status = "FAIL (Validation Failed)"
        except Exception as e:
            print(f"  [FAIL] Validation Exception: {e}")
            all_passed = False
            status = "FAIL (Validation Error)"
            total_time = time.time() - start_time
            
        summaries.append({
            "name": benchmark["name"],
            "status": status,
            "time": total_time,
            "triangles": len(triangles),
            "watertight": validation.get("watertight", False) if 'validation' in locals() else False
        })
        
        # Optional: Save STL for inspection
        try:
            clean_name = benchmark["name"].split(" ")[0].replace(",", "").lower()
            output_path = f"eval_output_{clean_name}.stl"
            write_binary_stl(output_path, triangles)
            if os.path.exists(output_path):
                os.remove(output_path)
        except Exception as e:
            print(f"  [WARN] Failed to write test STL file: {e}")

    # Print Final Summary Table
    print("\n" + "=" * 80)
    print("EVALUATION SUMMARY")
    print("=" * 80)
    print(f"{'Location/Benchmark':<35} | {'Status':<25} | {'Time (s)':<8} | {'Triangles':<10}")
    print("-" * 80)
    for summary in summaries:
        print(f"{summary['name']:<35} | {summary['status']:<25} | {summary['time']:<8.2f} | {summary['triangles']:<10}")
    print("=" * 80)
    
    if all_passed:
        print("ALL TESTS PASSED! Mesh engine is 100% mathematically watertight and reliable.")
    else:
        print("SOME TESTS FAILED. Please check log messages above.")
        
    return all_passed

def run_security_policy_tests() -> bool:
    print("\n" + "=" * 80)
    print("RUNNING SECURITY POLICY TESTS")
    print("=" * 80)
    
    from harness.policy_server import PolicyService
    passed = True
    
    # 1. Structural Gating - viewer tries to run shell command
    try:
        p_viewer = PolicyService(role="viewer", env="production")
        if p_viewer.is_tool_allowed("raw_shell_execute"):
            print("  [FAIL] Structural Gating: 'viewer' role was allowed to run 'raw_shell_execute'")
            passed = False
        else:
            print("  [PASS] Structural Gating: 'viewer' role blocked from 'raw_shell_execute'")
            
        # viewer runs allowed tool
        if not p_viewer.is_tool_allowed("geocode_address"):
            print("  [FAIL] Structural Gating: 'viewer' role blocked from allowed tool 'geocode_address'")
            passed = False
        else:
            print("  [PASS] Structural Gating: 'viewer' role allowed to run 'geocode_address'")
    except Exception as e:
        print(f"  [FAIL] Structural Gating test failed with exception: {e}")
        passed = False
        
    # 2. Structural Gating - admin in production environment tries to run blocked tool
    try:
        p_admin_prod = PolicyService(role="admin", env="production")
        if p_admin_prod.is_tool_allowed("raw_shell_execute"):
            print("  [FAIL] Structural Gating: 'admin' role in 'production' allowed to run blocked 'raw_shell_execute'")
            passed = False
        else:
            print("  [PASS] Structural Gating: 'admin' role in 'production' blocked from 'raw_shell_execute'")
    except Exception as e:
        print(f"  [FAIL] Structural Gating admin/prod test failed: {e}")
        passed = False

    # 3. Semantic Gating - checking restricted Area 51 coordinates
    try:
        p_gating = PolicyService(role="viewer", env="production")
        unsafe_args = {"center_lat": 37.23, "center_lon": -115.80}
        if p_gating.check_action_semantic("get_elevation_grid", unsafe_args):
            print("  [FAIL] Semantic Gating: Area 51 query allowed")
            passed = False
        else:
            print("  [PASS] Semantic Gating: Area 51 query blocked")
            
        # Safe coordinates
        safe_args = {"center_lat": 41.2781, "center_lon": -72.5273}
        if not p_gating.check_action_semantic("get_elevation_grid", safe_args):
            print("  [FAIL] Semantic Gating: Safe Clinton coordinates blocked")
            passed = False
        else:
            print("  [PASS] Semantic Gating: Safe Clinton coordinates allowed")
    except Exception as e:
        print(f"  [FAIL] Semantic Gating test failed with exception: {e}")
        passed = False
        
    return passed

def run_self_repair_test() -> bool:
    print("\n" + "=" * 80)
    print("RUNNING GREEN TEAM SELF-REPAIR TEST")
    print("=" * 80)
    
    import topo_agent
    
    original_validate = topo_agent.validate_mesh
    
    call_count = 0
    def mock_validate(vertices, faces):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            print(f"  [MOCK] First validation call: returning invalid (watertight=False) to trigger repair.")
            return {
                "valid": False,
                "watertight": False,
                "volume": 0.0,
                "errors": ["Mocked mesh validation failure: open edges found"]
            }
        else:
            print(f"  [MOCK] Subsequent validation call {call_count}: running original validation.")
            return original_validate(vertices, faces)
            
    # Monkey-patch validate_mesh in topo_agent
    topo_agent.validate_mesh = mock_validate
    
    passed = False
    try:
        print("  Triggering topo_agent pipeline with mocked validator...")
        success = topo_agent.run_pipeline(
            address_or_coords="41.2781, -72.5273",
            width_m=50,
            height_m=50,
            resolution=10,
            model_width_mm=50.0,
            base_thickness_mm=2.0,
            z_exaggeration=2.0,
            output_stl="test_repair.stl",
            output_html="test_repair.html",
            clip_to_parcel=False
        )
        
        # Clean up files
        for fpath in ["test_repair.stl", "test_repair.html"]:
            if os.path.exists(fpath):
                os.remove(fpath)
                
        if success and call_count > 1:
            print(f"  [PASS] Self-repair triggered! Validator called {call_count} times and pipeline completed successfully.")
            passed = True
        else:
            print(f"  [FAIL] Self-repair test failed. success={success}, call_count={call_count}")
    except Exception as e:
        print(f"  [FAIL] Self-repair test raised exception: {e}")
    finally:
        topo_agent.validate_mesh = original_validate
        
    return passed

def run_exact_boundary_clinton_test() -> bool:
    print("\n" + "=" * 80)
    print("RUNNING EXACT BOUNDARY PARCEL TEST: 242 EAST MAIN STREET, CLINTON, CT")
    print("=" * 80)
    
    import topo_agent
    
    passed = False
    try:
        output_stl = "clinton_town_hall_test.stl"
        output_html = "clinton_town_hall_test.html"
        
        # Run the full pipeline for Clinton Town Hall with high-res UConn LiDAR
        success = topo_agent.run_pipeline(
            address_or_coords="242 East Main Street, Clinton, CT",
            width_m=200,
            height_m=200,
            resolution=40,
            model_width_mm=100.0,
            base_thickness_mm=3.0,
            z_exaggeration=2.0,
            output_stl=output_stl,
            output_html=output_html,
            clip_to_parcel=True
        )
        
        if not success:
            print("  [FAIL] TopoTwin pipeline failed to run successfully.")
            return False
            
        # Verify generated STL is watertight and has positive volume using Trimesh
        if os.path.exists(output_stl):
            mesh = trimesh.load(output_stl)
            is_watertight = mesh.is_watertight
            volume = mesh.volume
            
            print(f"  [METRICS] Watertight: {is_watertight}, Volume: {volume:.2f} cubic units")
            
            if is_watertight and volume > 0:
                print("  [PASS] Successfully verified watertight exact-boundary STL with positive volume.")
                passed = True
            else:
                print(f"  [FAIL] Geometry check failed: watertight={is_watertight}, volume={volume}")
        else:
            print("  [FAIL] Output STL file was not created.")
            
        # Clean up files
        for fpath in [output_stl, output_html]:
            if os.path.exists(fpath):
                os.remove(fpath)
    except Exception as e:
        print(f"  [FAIL] Test raised exception: {e}")
        
    return passed

if __name__ == "__main__":
    # 1. Run standard evaluation benchmarks
    benchmarks_success = run_evaluation_suite(resolution=20)
    
    # 2. Run security policy tests
    security_success = run_security_policy_tests()
    
    # 3. Run green team self-repair tests
    repair_success = run_self_repair_test()
    
    # 4. Run exact-boundary 9 Marian Lane test
    clinton_success = run_exact_boundary_clinton_test()
    
    all_success = benchmarks_success and security_success and repair_success and clinton_success
    
    print("\n" + "=" * 80)
    print("FINAL EVALUATION SUITE STATUS")
    print("=" * 80)
    print(f"Benchmarks: {'PASSED' if benchmarks_success else 'FAILED'}")
    print(f"Security Policies: {'PASSED' if security_success else 'FAILED'}")
    print(f"Self-Repair Loop: {'PASSED' if repair_success else 'FAILED'}")
    print(f"Clinton Town Hall Exact-Parcel: {'PASSED' if clinton_success else 'FAILED'}")
    print("-" * 80)
    print(f"OVERALL STATUS: {'SUCCESS' if all_success else 'FAILURE'}")
    print("=" * 80)
    
    sys.exit(0 if all_success else 1)
