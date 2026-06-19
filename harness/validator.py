import numpy as np
import trimesh

try:
    import open3d as o3d
except ImportError:
    o3d = None

class MeshValidator:
    """
    Quality control gateway preventing malformed data from advancing downstream 
    to 3D slicing engines or architectural CAD layers.
    """
    
    @staticmethod
    def validate_and_export(vertices: np.ndarray, faces: np.ndarray, output_path: str, decimation_target: int = 0):
        """
        Instantiates a Trimesh object, interrogates topological stability metrics, 
        optionally simplifies via Quadric Error Metrics, and exports to disk.
        """
        # Construct Trimesh entity natively
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
        
        # 1. Topological Guarantees
        is_watertight = mesh.is_watertight
        mesh_volume = mesh.volume
        is_volume_positive = mesh_volume > 0
        
        print(f"Validation Metrics:\n - Watertight Manifold: {is_watertight}\n - Volume: {mesh_volume:.2f} cubic units")
        
        if not is_watertight:
            raise ValueError("Topology Error: Extruded mesh contains non-manifold edges or holes.")
            
        if not is_volume_positive:
            raise ValueError("Topology Error: Mesh winding dictates negative volume. Normals inverted.")
            
        # 2. Downstream Decimation (Quadric Error Metrics via Open3D)
        if decimation_target > 0 and len(mesh.faces) > decimation_target:
            if o3d is None:
                print("Warning: Open3D not installed. Skipping decimation pass.")
            else:
                print(f"Applying QEM Decimation. Target Faces: {decimation_target}")
                
                o3d_mesh = o3d.geometry.TriangleMesh()
                o3d_mesh.vertices = o3d.utility.Vector3dVector(mesh.vertices)
                o3d_mesh.triangles = o3d.utility.Vector3iVector(mesh.faces)
                
                simplified = o3d_mesh.simplify_quadric_decimation(target_number_of_triangles=decimation_target)
                
                mesh = trimesh.Trimesh(
                    vertices=np.asarray(simplified.vertices),
                    faces=np.asarray(simplified.triangles)
                )
                
                if not mesh.is_watertight:
                    print("Warning: Decimation generated minor manifold breaks. Falling back to non-decimated structural mesh.")
                    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)

        # 3. Serialization
        mesh.export(output_path)
        print(f"Success: Exact-boundary mesh fully validated and written to {output_path}.")
        return mesh

def validate_mesh(vertices: np.ndarray, faces: np.ndarray) -> dict:
    """
    Verifies watertightness (manifoldness) and signed volume using trimesh.
    Maintains compatibility with orchestrator checks.
    """
    results = {
        "valid": True,
        "watertight": True,
        "volume": 0.0,
        "errors": []
    }
    try:
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
        results["watertight"] = mesh.is_watertight
        results["volume"] = float(mesh.volume)
        
        if not mesh.is_watertight:
            results["valid"] = False
            results["errors"].append("Mesh is not a closed watertight manifold (has open edges or non-manifold vertices).")
        if mesh.volume <= 0:
            results["valid"] = False
            results["errors"].append(f"Mesh has invalid signed volume: {mesh.volume:.2f} (winding order or normal orientation issue).")
    except Exception as e:
        results["valid"] = False
        results["errors"].append(f"Trimesh validation error: {e}")
        
    return results

if __name__ == "__main__":
    # Test validator with a closed cube
    vertices = np.array([
        [0,0,0], [1,0,0], [1,1,0], [0,1,0],
        [0,0,1], [1,0,1], [1,1,1], [0,1,1]
    ], dtype=np.float32)
    # 12 triangles forming a cube (CCW looking from outside)
    faces = np.array([
        [0, 2, 1], [0, 3, 2], # Bottom
        [4, 5, 6], [4, 6, 7], # Top
        [0, 1, 5], [0, 5, 4], # Front
        [2, 3, 7], [2, 7, 6], # Back
        [3, 0, 4], [3, 4, 7], # Left
        [1, 2, 6], [1, 6, 5]  # Right
    ], dtype=np.int32)
    
    res = validate_mesh(vertices, faces)
    print("Cube Validation Results:")
    print(f"  Valid: {res['valid']}")
    print(f"  Watertight: {res['watertight']}")
    print(f"  Volume: {res['volume']}")
    print(f"  Errors: {res['errors']}")
