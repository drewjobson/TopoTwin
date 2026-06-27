import plotly.graph_objects as go
import numpy as np
from shapely.geometry import shape, Polygon as ShapelyPolygon

def create_plotly_visual(
    triangles: list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]],
    output_html: str,
    title: str = "TopoTwin 3D Property Topology Twin",
    polygon_coords: list[tuple[float, float, float]] = None,
    colorscale: str = "earth",
    render_mode: str = "Solid"
) -> go.Figure:
    """Generates an interactive 3D HTML visualization of the generated mesh using Plotly.
    
    Args:
        triangles (list): List of triangles.
        output_html (str): File path to save the HTML file.
        title (str): Title for the visualization.
        polygon_coords (list): 3D coordinates for property outline.
        colorscale (str): Colormap scheme (e.g. Viridis, Earth, Terrain).
        render_mode (str): Rendering style ("Solid", "Wireframe", "Solid + Wireframe", "Solid + Contours").
    """
    if not triangles:
        print("No triangles to visualize.")
        return go.Figure()

    # Extract unique vertices and index mapping
    vertices = []
    vertex_map = {}
    i_indices = []
    j_indices = []
    k_indices = []
    
    for tri in triangles:
        tri_idx = []
        for v in tri:
            v_key = (round(v[0], 5), round(v[1], 5), round(v[2], 5))
            if v_key not in vertex_map:
                vertex_map[v_key] = len(vertices)
                vertices.append(v)
            tri_idx.append(vertex_map[v_key])
        i_indices.append(tri_idx[0])
        j_indices.append(tri_idx[1])
        k_indices.append(tri_idx[2])
        
    x = [v[0] for v in vertices]
    y = [v[1] for v in vertices]
    z = [v[2] for v in vertices]
    
    print(f"Creating 3D plot from {len(vertices)} unique vertices...")
    
    traces = []
    
    # 1. Create Mesh Trace (Solid) if requested
    if "Solid" in render_mode:
        mesh_trace = go.Mesh3d(
            x=x, y=y, z=z,
            i=i_indices, j=j_indices, k=k_indices,
            intensity=z,  # Color by height
            colorscale=colorscale.lower(),
            colorbar=dict(title="Height (mm)", tickfont=dict(color="#F1F0EA")),
            name="Terrain Mesh",
            showscale=True,
            flatshading=True,  # Faceted aesthetic
            lighting=dict(
                ambient=0.4,
                diffuse=0.8,
                specular=0.1,
                roughness=0.8,
                fresnel=0.2
            ),
            lightposition=dict(
                x=1000,
                y=1000,
                z=2000
            )
        )
        traces.append(mesh_trace)

    # 2. Create Wireframe Trace if requested
    if "Wireframe" in render_mode:
        edge_x = []
        edge_y = []
        edge_z = []
        for tri in triangles:
            v1, v2, v3 = tri
            edge_x.extend([v1[0], v2[0], v3[0], v1[0], None])
            edge_y.extend([v1[1], v2[1], v3[1], v1[1], None])
            edge_z.extend([v1[2], v2[2], v3[2], v1[2], None])
            
        wireframe_trace = go.Scatter3d(
            x=edge_x, y=edge_y, z=edge_z,
            mode="lines",
            line=dict(color="#888888" if "Solid" in render_mode else "#E65100", width=1),
            name="Wireframe",
            hoverinfo="skip"
        )
        traces.append(wireframe_trace)

    # 3. Create Contour Lines Trace if requested
    if "Contours" in render_mode:
        z_min, z_max = np.min(z), np.max(z)
        contour_step = (z_max - z_min) / 15
        contour_levels = np.arange(z_min, z_max, contour_step) if contour_step > 0 else []
        
        contour_x = []
        contour_y = []
        contour_z = []
        
        for z_c in contour_levels:
            for tri in triangles:
                v1, v2, v3 = tri
                pts = []
                for edge in [(v1, v2), (v2, v3), (v3, v1)]:
                    e1, e2 = edge
                    if min(e1[2], e2[2]) <= z_c <= max(e1[2], e2[2]) and e1[2] != e2[2]:
                        t = (z_c - e1[2]) / (e2[2] - e1[2])
                        x_i = e1[0] + t * (e2[0] - e1[0])
                        y_i = e1[1] + t * (e2[1] - e1[1])
                        pts.append((x_i, y_i, z_c))
                if len(pts) >= 2:
                    contour_x.extend([pts[0][0], pts[1][0], None])
                    contour_y.extend([pts[0][1], pts[1][1], None])
                    contour_z.extend([pts[0][2], pts[1][2], None])
                    
        if contour_x:
            contour_trace = go.Scatter3d(
                x=contour_x, y=contour_y, z=contour_z,
                mode="lines",
                line=dict(color="#00E5FF", width=2.5),
                name="Contour Lines",
                hoverinfo="skip"
            )
            traces.append(contour_trace)
            
    # 4. Property Boundary Outline
    if polygon_coords:
        boundary_trace = go.Scatter3d(
            x=[pt[0] for pt in polygon_coords],
            y=[pt[1] for pt in polygon_coords],
            z=[pt[2] for pt in polygon_coords],
            mode="lines",
            line=dict(color="#F59E0B" if "Contours" in render_mode else "#E65100", width=6),
            name="Property Boundary"
        )
        traces.append(boundary_trace)
        
    fig = go.Figure(data=traces)
    
    # Configure 3D scene options
    fig.update_layout(
        title=title,
        scene=dict(
            xaxis=dict(title="Width (X mm)", gridcolor="rgba(255, 255, 255, 0.1)", color="#F1F0EA"),
            yaxis=dict(title="Length (Y mm)", gridcolor="rgba(255, 255, 255, 0.1)", color="#F1F0EA"),
            zaxis=dict(title="Elevation (Z mm)", gridcolor="rgba(255, 255, 255, 0.1)", color="#F1F0EA"),
            aspectmode="data",  # Keep physical proportions correct!
            bgcolor="#181A1B"  # Charcoal matte dark background
        ),
        paper_bgcolor="#181A1B",
        font=dict(color="#F1F0EA"),
        margin=dict(l=0, r=0, b=0, t=40)
    )
    
    print(f"Saving interactive 3D model to '{output_html}'...")
    fig.write_html(output_html)
    print("Visualization saved successfully.")
    return fig
