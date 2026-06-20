import plotly.graph_objects as go
import numpy as np

def create_plotly_visual(
    triangles: list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]],
    output_html: str,
    title: str = "TopoTwin 3D Property Topology Twin",
    polygon_coords: list[tuple[float, float, float]] = None
) -> None:
    """Generates an interactive 3D HTML visualization of the generated mesh using Plotly.
    
    Args:
        triangles (list): List of triangles.
        output_html (str): File path to save the HTML file.
        title (str): Title for the visualization.
    """
    if not triangles:
        print("No triangles to visualize.")
        return

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
    
    # Create the 3D mesh trace
    mesh_trace = go.Mesh3d(
        x=x, y=y, z=z,
        i=i_indices, j=j_indices, k=k_indices,
        intensity=z,  # Color by height
        colorscale="earth",  # Earthy terrain colors
        colorbar=dict(title="Height (mm)"),
        name="Terrain Mesh",
        showscale=True,
        flatshading=True,  # Gives a nice faceted 3D printing aesthetic
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
    
    traces = [mesh_trace]
    if polygon_coords:
        boundary_trace = go.Scatter3d(
            x=[pt[0] for pt in polygon_coords],
            y=[pt[1] for pt in polygon_coords],
            z=[pt[2] for pt in polygon_coords],
            mode="lines",
            line=dict(color="red", width=6),
            name="Property Boundary"
        )
        traces.append(boundary_trace)
        
    fig = go.Figure(data=traces)
    
    # Configure 3D scene options
    fig.update_layout(
        title=title,
        scene=dict(
            xaxis=dict(title="Width (X mm)", gridcolor="lightgray"),
            yaxis=dict(title="Length (Y mm)", gridcolor="lightgray"),
            zaxis=dict(title="Elevation (Z mm)", gridcolor="lightgray"),
            aspectmode="data",  # Keep physical proportions correct!
            bgcolor="rgb(10, 15, 30)"  # Sleek dark theme
        ),
        paper_bgcolor="rgb(10, 15, 30)",
        font=dict(color="white"),
        margin=dict(l=0, r=0, b=0, t=40)
    )
    
    print(f"Saving interactive 3D model to '{output_html}'...")
    fig.write_html(output_html)
    print("Visualization saved successfully.")
    return fig

if __name__ == "__main__":
    # Test visualization with a simple pyramid
    test_triangles = [
        # Base
        ((0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (5.0, 5.0, 5.0)),
        ((10.0, 0.0, 0.0), (10.0, 10.0, 0.0), (5.0, 5.0, 5.0)),
        ((10.0, 10.0, 0.0), (0.0, 10.0, 0.0), (5.0, 5.0, 5.0)),
        ((0.0, 10.0, 0.0), (0.0, 0.0, 0.0), (5.0, 5.0, 5.0))
    ]
    try:
        create_plotly_visual(test_triangles, "test_visual.html")
        import os
        if os.path.exists("test_visual.html"):
            os.remove("test_visual.html")
    except Exception as e:
        print(f"Test failed: {e}")
