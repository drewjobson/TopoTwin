import numpy as np
from scipy.spatial import Delaunay
from shapely.geometry import shape, Polygon as ShapelyPolygon, MultiPolygon as ShapelyMultiPolygon
from shapely import contains_xy
from typing import Tuple
from tools.parcel_service import is_point_in_polygon

class ManifoldMeshBuilder:
    """
    Constructs an exact-boundary 3D manifold mesh via 2D Delaunay triangulation 
    and multi-surface geometric extrusion.
    """
    
    def __init__(self, parcel_geometry_geojson: dict, thickness_meters: float = 5.0):
        # Parse the GeoJSON geometry into a Shapely object
        if isinstance(parcel_geometry_geojson, dict):
            self.poly_shape = shape(parcel_geometry_geojson)
        else:
            self.poly_shape = parcel_geometry_geojson
        self.thickness = thickness_meters
        self._init_boundary_path()

    def _init_boundary_path(self):
        """Constructs a matplotlib.path.Path representing the boundary (with path codes)
        to handle multi-part features (islands, multi-polygons) cleanly.
        """
        from matplotlib.path import Path
        
        vertices = []
        codes = []
        
        def add_ring(ring):
            coords = list(ring.coords)
            if not coords:
                return
            vertices.append(coords[0])
            codes.append(Path.MOVETO)
            for pt in coords[1:-1]:
                vertices.append(pt)
                codes.append(Path.LINETO)
            vertices.append(coords[-1])
            codes.append(Path.CLOSEPOLY)
            
        if isinstance(self.poly_shape, ShapelyPolygon):
            add_ring(self.poly_shape.exterior)
            for hole in self.poly_shape.interiors:
                add_ring(hole)
        elif isinstance(self.poly_shape, ShapelyMultiPolygon):
            for sub_poly in self.poly_shape.geoms:
                add_ring(sub_poly.exterior)
                for hole in sub_poly.interiors:
                    add_ring(hole)
                    
        if vertices:
            self.boundary_path = Path(np.array(vertices)[:, :2], codes)
        else:
            self.boundary_path = None

    def _extract_boundary_edges(self, simplices: np.ndarray) -> np.ndarray:
        """
        Extracts the ordered loop of boundary edges from a triangulated surface.
        A boundary edge is defined topologically as an edge shared by exactly one simplex.
        """
        edges = np.vstack((
            simplices[:, [0, 1]],
            simplices[:, [1, 2]],
            simplices[:, [2, 0]]
        ))
        
        # Sort each edge so [a, b] matches [b, a] for frequency counting
        sorted_edges = np.sort(edges, axis=1)
        
        unique_edges, counts = np.unique(sorted_edges, axis=0, return_counts=True)
        boundary_edges_undirected = unique_edges[counts == 1]
        
        # Optimize directed boundary edge lookup using a set of tuples
        boundary_set = {tuple(edge) for edge in boundary_edges_undirected}
        
        directed_boundary = []
        for d_edge in edges:
            if tuple(sorted(d_edge)) in boundary_set:
                directed_boundary.append(d_edge)
                
        return np.array(directed_boundary)

    def build_mesh(self, points_2d: np.ndarray, elevations_m: np.ndarray, model_width_mm: float, z_exaggeration: float) -> Tuple[np.ndarray, np.ndarray]:
        """
        Executes Delaunay triangulation, centroid masking, and 3D solid extrusion.
        Returns vertices and faces arrays. Coordinates are scaled to model size.
        """
        # 1. Triangulation of the 2D point cloud
        tri = Delaunay(points_2d)
        simplices = tri.simplices
        
        # 2. Vectorized Point-in-Polygon Centroid Filtering using shapely.contains_xy
        v1 = points_2d[simplices[:, 0]]
        v2 = points_2d[simplices[:, 1]]
        v3 = points_2d[simplices[:, 2]]
        centroids = (v1 + v2 + v3) / 3.0
        
        inside_mask = contains_xy(self.poly_shape, centroids[:, 0], centroids[:, 1])
        top_faces = simplices[inside_mask]
        
        # Get bounds for scaling
        min_x, min_y, max_x, max_y = self.poly_shape.bounds
        width_ft = max_x - min_x
        
        # Conversion factor to model coordinates (mm)
        # points_2d is in State Plane Feet
        # model_width_mm is in mm.
        model_scale = model_width_mm / (width_ft * 0.3048)  # scaling real meters to model mm
        
        # Scale XY to meters first, then to model scale
        X_scaled = (points_2d[:, 0] * 0.3048) * model_scale
        Y_scaled = (points_2d[:, 1] * 0.3048) * model_scale
        Z_scaled = elevations_m * z_exaggeration * model_scale
        
        point_cloud_3d = np.column_stack((X_scaled, Y_scaled, Z_scaled))
        
        # 3. Extrusion baseline
        z_min = np.min(Z_scaled)
        # thickness is in meters, scale to model mm
        thickness_mm = self.thickness * z_exaggeration * model_scale
        z_base = z_min - thickness_mm
        
        num_vertices = len(point_cloud_3d)
        
        # Top vertices
        top_vertices = np.copy(point_cloud_3d)
        
        # Bottom vertices
        bottom_vertices = np.copy(point_cloud_3d)
        bottom_vertices[:, 2] = z_base
        
        all_vertices = np.vstack((top_vertices, bottom_vertices))
        
        # 4. Faces Construction
        # Top surface (CCW winding)
        faces_top = top_faces
        
        # Bottom surface (CW winding)
        faces_bottom = top_faces + num_vertices
        faces_bottom = faces_bottom[:, [0, 2, 1]]
        
        # Skirt walls (outward facing normals)
        boundary_edges = self._extract_boundary_edges(top_faces)
        skirt_faces = []
        
        for edge in boundary_edges:
            v_a = edge[0]
            v_b = edge[1]
            
            v_a_prime = v_a + num_vertices
            v_b_prime = v_b + num_vertices
            
            # Outward facing winding order (v_a, v_b_prime, v_b) and (v_a, v_a_prime, v_b_prime)
            skirt_faces.append([v_a, v_b_prime, v_b])
            skirt_faces.append([v_a, v_a_prime, v_b_prime])
            
        faces_skirt = np.array(skirt_faces)
        
        all_faces = np.vstack((faces_top, faces_bottom, faces_skirt))
        
        # Selective Origin Shift: shift X and Y only to start at 0
        min_x_scaled = np.min(all_vertices[:, 0])
        min_y_scaled = np.min(all_vertices[:, 1])
        all_vertices[:, 0] -= min_x_scaled
        all_vertices[:, 1] -= min_y_scaled
        
        # Downcast to float32 immediately before returning
        return all_vertices.astype(np.float32), all_faces.astype(np.int32)

# --- Backward compatibility & Out-of-State Fallback ---

def build_solid_mesh(
    elevations: np.ndarray, 
    dx_m: float, 
    dy_m: float, 
    model_width_mm: float = 100.0, 
    base_thickness_mm: float = 2.0, 
    z_exaggeration: float = 2.0,
    lats: np.ndarray = None,
    lons: np.ndarray = None,
    polygon: list[list[float]] = None,
    border_thickness_mm: float = 0.8
) -> list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]]:
    """Extrudes a 2D elevation grid into a solid watertight 3D mesh.
    
    Used for rectangular bounding box fallbacks.
    """
    R, C = elevations.shape
    real_width_m = (C - 1) * dx_m
    model_scale = model_width_mm / real_width_m if real_width_m > 0 else 1.0
    
    X = np.zeros((R, C))
    Y = np.zeros((R, C))
    Z = np.zeros((R, C))
    
    for r in range(R):
        for c in range(C):
            X[r, c] = c * dx_m * model_scale
            Y[r, c] = r * dy_m * model_scale
            Z[r, c] = elevations[r, c] * z_exaggeration * model_scale
            
    inside_mask = np.ones((R, C), dtype=bool)
    if polygon is not None and lats is not None and lons is not None:
        for r in range(R):
            for c in range(C):
                inside_mask[r, c] = is_point_in_polygon(lons[c], lats[r], polygon)
                
    if not np.any(inside_mask):
        inside_mask = np.ones((R, C), dtype=bool)
        
    z_min_inside = np.min(Z[inside_mask])
    z_base = z_min_inside - base_thickness_mm
    
    if polygon is not None and lats is not None and lons is not None:
        for r in range(R):
            for c in range(C):
                if not inside_mask[r, c]:
                    Z[r, c] = z_base + border_thickness_mm

    triangles = []
    
    # 1. Top Surface (CCW winding looking from +Z)
    for r in range(R - 1):
        for c in range(C - 1):
            p00 = (X[r, c], Y[r, c], Z[r, c])
            p01 = (X[r, c+1], Y[r, c+1], Z[r, c+1])
            p10 = (X[r+1, c], Y[r+1, c], Z[r+1, c])
            p11 = (X[r+1, c+1], Y[r+1, c+1], Z[r+1, c+1])
            
            triangles.append((p00, p01, p10))
            triangles.append((p01, p11, p10))
            
    # 2. Bottom Surface (CW winding looking from +Z)
    for r in range(R - 1):
        for c in range(C - 1):
            b00 = (X[r, c], Y[r, c], z_base)
            b01 = (X[r, c+1], Y[r, c+1], z_base)
            b10 = (X[r+1, c], Y[r+1, c], z_base)
            b11 = (X[r+1, c+1], Y[r+1, c+1], z_base)
            
            triangles.append((b00, b10, b01))
            triangles.append((b01, b10, b11))
            
    # Helper for vertical walls
    def add_wall_quad(ax, ay, az_top, bx, by, bz_top):
        a_top = (ax, ay, az_top)
        b_top = (bx, by, bz_top)
        a_bot = (ax, ay, z_base)
        b_bot = (bx, by, z_base)
        triangles.append((a_bot, b_bot, a_top))
        triangles.append((b_bot, b_top, a_top))
        
    # 3. Side Walls
    for c in range(C - 1):
        add_wall_quad(X[0, c], Y[0, c], Z[0, c], X[0, c+1], Y[0, c+1], Z[0, c+1])
        
    for r in range(R - 1):
        add_wall_quad(X[r, C-1], Y[r, C-1], Z[r, C-1], X[r+1, C-1], Y[r+1, C-1], Z[r+1, C-1])
        
    for c in range(C - 1, 0, -1):
        add_wall_quad(X[R-1, c], Y[R-1, c], Z[R-1, c], X[R-1, c-1], Y[R-1, c-1], Z[R-1, c-1])
        
    for r in range(R - 1, 0, -1):
        add_wall_quad(X[r, 0], Y[r, 0], Z[r, 0], X[r-1, 0], Y[r-1, 0], Z[r-1, 0])
        
    return triangles

def triangles_to_mesh(triangles) -> tuple[np.ndarray, np.ndarray]:
    """Convert a list of triangle tuples (each containing 3 vertices of 3 coordinates)
    into a tuple of (vertices, faces) numpy arrays, merging duplicate vertices.
    """
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
    return vertices, faces

def mesh_to_triangles(vertices: np.ndarray, faces: np.ndarray) -> list:
    """Convert (vertices, faces) arrays back to list of triangle tuples."""
    return [
        (tuple(vertices[f[0]]), tuple(vertices[f[1]]), tuple(vertices[f[2]]))
        for f in faces
    ]


