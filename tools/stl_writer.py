import math
import struct

def compute_normal(
    v1: tuple[float, float, float], 
    v2: tuple[float, float, float], 
    v3: tuple[float, float, float]
) -> tuple[float, float, float]:
    """Computes the normal vector for a triangle defined by three vertices (v1, v2, v3).
    
    The normal points outwards according to the counter-clockwise winding order.
    """
    ux, uy, uz = v2[0] - v1[0], v2[1] - v1[1], v2[2] - v1[2]
    vx, vy, vz = v3[0] - v1[0], v3[1] - v1[1], v3[2] - v1[2]
    
    # Cross product
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    
    # Normalize
    length = math.sqrt(nx*nx + ny*ny + nz*nz)
    if length > 1e-9:
        return (nx / length, ny / length, nz / length)
    return (0.0, 0.0, 0.0)

def write_binary_stl(
    filepath: str, 
    triangles: list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]]
) -> None:
    """Writes a list of triangles to a binary STL file.
    
    Args:
        filepath (str): Target output file path.
        triangles (list): List of triangles. Each triangle is a tuple of 3 vertices,
                          where each vertex is a tuple of 3 floats: (x, y, z).
    """
    header = b"TopoTwin STL Exporter - Automated Agentic Generation".ljust(80, b"\0")[:80]
    num_triangles = len(triangles)
    
    print(f"Writing {num_triangles} triangles to binary STL file '{filepath}'...")
    
    with open(filepath, "wb") as f:
        # 80-byte header
        f.write(header)
        # 4-byte unsigned integer indicating number of triangles
        f.write(struct.pack("<I", num_triangles))
        
        # 50 bytes per triangle
        for tri in triangles:
            v1, v2, v3 = tri
            nx, ny, nz = compute_normal(v1, v2, v3)
            
            # Pack data format: 12 floats (3 normal, 9 vertex coordinates) + 1 unsigned short (2 bytes attribute)
            packed_data = struct.pack(
                "<12fH",
                nx, ny, nz,
                v1[0], v1[1], v1[2],
                v2[0], v2[1], v2[2],
                v3[0], v3[1], v3[2],
                0
            )
            f.write(packed_data)
            
    print("STL write completed successfully.")

if __name__ == "__main__":
    # Test STL writer with a single triangle (a simple flat wedge)
    test_triangles = [
        ((0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0))
    ]
    try:
        write_binary_stl("test.stl", test_triangles)
        print("Success! Generated test.stl")
        import os
        if os.path.exists("test.stl"):
            os.remove("test.stl")
    except Exception as e:
        print(f"Test failed: {e}")
