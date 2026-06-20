import streamlit as st
import numpy as np
import os
import asyncio
import trimesh
from shapely.geometry import shape, Polygon as ShapelyPolygon, MultiPolygon as ShapelyMultiPolygon
import io

from tools.geocoder import geocode_address, clean_address
from tools.parcel_service import query_ct_parcel
from tools.dem_downloader import DEMDownloader, get_elevation_grid, calculate_grid_bounds
from tools.mesh_builder import ManifoldMeshBuilder, build_solid_mesh
from harness.validator import validate_mesh
from visualizer import create_plotly_visual

# Page Configuration
st.set_page_config(
    page_title="TopoPlot: Interactive 3D Terrain & Exact-Parcel Mesh Generator",
    page_icon="🌟",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom Glassmorphic Light styling injection
st.markdown(
    """
    <style>
    /* Earthy Light Theme styling */
    .stApp {
        background-color: #F3F4F6;
        color: #1F2937;
    }
    
    /* Glowing Contour Title */
    .gradient-title {
        background: linear-gradient(135deg, #E65100 0%, #D97706 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.8rem;
        font-weight: 800;
        margin-bottom: 0.2rem;
    }
    
    .gradient-subtitle {
        color: #4B5563;
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }
    
    /* Custom container card style (White) */
    .glass-card {
        background-color: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
    }
    
    /* Style the native Streamlit containers (White cards) */
    div[data-testid="stVerticalBlockBorder"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E5E7EB !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03) !important;
        padding: 24px !important;
    }
    
    /* Highlight indicators */
    .indicator-label {
        font-size: 0.85rem;
        color: #4B5563;
        margin-bottom: 4px;
    }
    
    .indicator-value {
        font-size: 1.4rem;
        font-weight: 700;
        color: #E65100;
    }
    
    /* Secondary Buttons Styling */
    .stButton > button {
        background-color: #FFFFFF !important;
        color: #374151 !important;
        border: 1px solid #D1D5DB !important;
        border-radius: 8px !important;
        transition: background-color 0.2s ease, border-color 0.2s ease !important;
    }
    .stButton > button:hover {
        background-color: #F9FAFB !important;
        border-color: #9CA3AF !important;
    }
    
    /* Primary Action CTA Button (Contour Line Orange) */
    div[data-testid="stButton"] button[kind="primary"] {
        background: linear-gradient(135deg, #E65100 0%, #D97706 100%) !important;
        color: #FFFFFF !important;
        border: none !important;
        font-weight: bold !important;
        box-shadow: 0 4px 6px -1px rgba(230, 81, 0, 0.2) !important;
    }
    div[data-testid="stButton"] button[kind="primary"]:hover {
        box-shadow: 0 10px 15px -3px rgba(230, 81, 0, 0.3) !important;
        opacity: 0.95 !important;
    }
    
    /* Download Button Center and Cartographic Orange Gradient */
    div[data-testid="stDownloadButton"] {
        display: flex;
        justify-content: center;
        margin-top: 15px;
    }
    div[data-testid="stDownloadButton"] button {
        background: linear-gradient(135deg, #E65100 0%, #D97706 100%) !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
        padding: 12px 28px !important;
        font-size: 1.05rem !important;
        box-shadow: 0 4px 6px -1px rgba(230, 81, 0, 0.2) !important;
        width: auto !important;
        min-width: 220px !important;
    }
    div[data-testid="stDownloadButton"] button:hover {
        box-shadow: 0 10px 15px -3px rgba(230, 81, 0, 0.3) !important;
        opacity: 0.95 !important;
    }
    
    /* Elevate Slider and Input Label Contrast */
    div[data-testid="stWidgetLabel"] p {
        color: #1F2937 !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
    }

    /* Force Light theme input borders and text colors */
    div[data-baseweb="input"] {
        background-color: #FFFFFF !important;
        border-color: #D1D5DB !important;
        color: #1F2937 !important;
    }
    input {
        color: #1F2937 !important;
        background-color: #FFFFFF !important;
    }
 
    /* Autocomplete Dropdown List Container & Buttons */
    .autocomplete-dropdown {
        background-color: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        padding: 8px;
        margin-top: -10px;
        margin-bottom: 15px;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        z-index: 100;
    }
    .autocomplete-dropdown div[data-testid="stButton"] button {
        background-color: transparent !important;
        color: #374151 !important;
        border: none !important;
        text-align: left !important;
        padding: 8px 12px !important;
        border-radius: 4px !important;
        font-size: 0.9rem !important;
        display: flex !important;
        justify-content: flex-start !important;
        width: 100% !important;
        margin: 0 !important;
    }
    .autocomplete-dropdown div[data-testid="stButton"] button:hover {
        background-color: #F3F4F6 !important;
        color: #E65100 !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

def run_async_loop(coro):
    """Utility to run an async coroutine synchronously inside Streamlit."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# ArcGIS suggest endpoints for CT-bounded real-time autocomplete
def get_arcgis_suggestions(text: str) -> list:
    if len(text) < 3:
        return []
    url = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/suggest"
    params = {
        "f": "json",
        "text": text,
        "searchExtent": "-73.727,40.982,-71.786,42.050",
        "maxSuggestions": 5
    }
    try:
        import requests
        r = requests.get(url, params=params, timeout=4)
        if r.status_code == 200:
            return r.json().get("suggestions", [])
    except Exception:
        pass
    return []

def resolve_arcgis_magic_key(magic_key: str, text: str) -> tuple[float, float, str] | None:
    url = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
    params = {
        "f": "json",
        "magicKey": magic_key,
        "singleLine": text,
        "maxLocations": 1
    }
    try:
        import requests
        r = requests.get(url, params=params, timeout=4)
        if r.status_code == 200:
            data = r.json()
            candidates = data.get("candidates", [])
            if candidates:
                candidate = candidates[0]
                loc = candidate.get("location", {})
                lon = loc.get("x")
                lat = loc.get("y")
                addr = candidate.get("address")
                if lat is not None and lon is not None:
                    return float(lat), float(lon), str(addr)
    except Exception:
        pass
    return None

# Initialize Session States for Autocomplete Handoff
if "selected_address" not in st.session_state:
    st.session_state["selected_address"] = "242 E Main St, Clinton, Connecticut, 06413"
if "selected_coords" not in st.session_state:
    st.session_state["selected_coords"] = (41.27137, -72.50441)
if "search_query" not in st.session_state:
    st.session_state["search_query"] = "242 East Main Street, Clinton, CT"

# App Header
st.markdown('<div class="gradient-title">🌟 TopoPlot 3D Terrain Generator</div>', unsafe_allow_html=True)
st.markdown('<div class="gradient-subtitle">Statewide Connecticut 2-Foot LiDAR Exact-Parcel Mesh Engine</div>', unsafe_allow_html=True)

# Main two-column layout
col_left, col_right = st.columns([1, 2], gap="large")

with col_left:
    with st.container(border=True):
        st.subheader("1. Address Search")
        
        address_input = st.text_input(
            "Search Connecticut Address (Autocomplete):",
            value=st.session_state["search_query"],
            help="Start typing any Connecticut address. Select the matching address from the dropdown list."
        )
        
        cleaned_query = clean_address(address_input)
        
        # Live Autocomplete Dropdown list
        suggestions = []
        if len(cleaned_query) >= 3:
            suggestions = get_arcgis_suggestions(cleaned_query)
            
        if suggestions:
            st.markdown('<div class="autocomplete-dropdown">', unsafe_allow_html=True)
            for idx, sug in enumerate(suggestions[:5]):
                if st.button(f"📍 {sug['text']}", key=f"sug_{idx}", use_container_width=True):
                    resolved = resolve_arcgis_magic_key(sug["magicKey"], sug["text"])
                    if resolved:
                        lat, lon, full_addr = resolved
                        st.session_state["selected_address"] = full_addr
                        st.session_state["selected_coords"] = (lat, lon)
                        st.session_state["search_query"] = sug["text"]
                        st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            
        # Standardized locked-in selection card (Coordinate Handoff)
        st.markdown(
            f"""
            <div style="background: rgba(230, 81, 0, 0.05); border: 1px solid rgba(230, 81, 0, 0.2); border-radius: 8px; padding: 12px; margin-top: 10px; margin-bottom: 15px;">
                <div class="indicator-label">Locked-In Property:</div>
                <div style="font-weight: 700; color: #1F2937; font-size: 0.95rem;">{st.session_state["selected_address"]}</div>
                <div class="indicator-label" style="margin-top: 4px;">Coordinate Handoff: {st.session_state["selected_coords"][0]:.5f}, {st.session_state["selected_coords"][1]:.5f}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
            
        st.markdown("**Try these municipal examples:**")
        col_ex1, col_ex2 = st.columns(2)
        with col_ex1:
            if st.button("Clinton Town Hall"):
                st.session_state["selected_address"] = "242 E Main St, Clinton, Connecticut, 06413"
                st.session_state["selected_coords"] = (41.27137, -72.50441)
                st.session_state["search_query"] = "242 East Main Street, Clinton, CT"
                st.rerun()
        with col_ex2:
            if st.button("Hartford City Hall"):
                st.session_state["selected_address"] = "550 Main St, Hartford, Connecticut, 06103"
                st.session_state["selected_coords"] = (41.76249, -72.67324)
                st.session_state["search_query"] = "550 Main Street, Hartford, CT"
                st.rerun()

    # Spacing between containers
    st.write("")

    with st.container(border=True):
        st.subheader("2. Model & Fidelity Settings")
        
        resolution = st.slider(
            "Grid Resolution (Fidelity):",
            min_value=15,
            max_value=120,
            value=45,
            step=5,
            help="Higher values increase triangle density (fidelity) for architects but increase DEM sampling duration."
        )
        
        z_exaggeration = st.slider(
            "Vertical Z-Exaggeration:",
            min_value=0.5,
            max_value=4.0,
            value=2.0,
            step=0.1,
            help="Scales elevation features to make topography more visible."
        )
        
        col_width, col_base = st.columns(2)
        with col_width:
            model_width_mm = st.number_input(
                "Print Width (mm):",
                min_value=30.0,
                max_value=250.0,
                value=100.0,
                step=10.0,
                help="Physical output model width in millimeters."
            )
        with col_base:
            base_thickness_mm = st.number_input(
                "Base Thickness (mm):",
                min_value=1.0,
                max_value=10.0,
                value=3.0,
                step=0.5,
                help="Solid vertical padding added beneath the minimum elevation level."
            )
            
        if model_width_mm > 220.0:
            st.warning(f"⚠️ **Hardware Constraint Warning**: A print width of {model_width_mm:.0f}mm exceeds the standard build volume of a Creality K1 (220mm). The model will require manual scaling down in OrcaSlicer to print successfully.")
            
        clip_to_parcel = st.checkbox(
            "Clip strictly to Legal Parcel Boundaries",
            value=True,
            help="Uncheck to generate a standard rectangular terrain tile instead."
        )
        
        generate_btn = st.button("Generate 3D Model", type="primary", use_container_width=True)

with col_right:
    if not generate_btn:
        with st.container(border=True):
            st.markdown("<div style='text-align: center; padding: 40px 20px;'>", unsafe_allow_html=True)
            st.markdown("<div style='font-size: 5rem; line-height: 1;'>🏔️</div>", unsafe_allow_html=True)
            st.markdown("<h3 style='margin-top: 20px; color: #1F2937;'>Ready to Generate</h3>", unsafe_allow_html=True)
            st.markdown("<p style='color: #4B5563;'>Configure your settings on the left and click <strong>Generate 3D Model</strong> to fetch Connecticut ImageServer LiDAR data and build a watertight STL terrain mesh.</p>", unsafe_allow_html=True)
            st.markdown(
                """
                <div style="background: rgba(230, 81, 0, 0.05); border: 1px solid rgba(230, 81, 0, 0.15); border-radius: 8px; padding: 16px; text-align: left; margin-top: 24px; color: #1F2937;">
                <strong>⚙️ OrcaSlicer & Creality K1 Recommendations:</strong><br>
                - Use the <strong>Arachne</strong> wall generator in OrcaSlicer to fill fine property edges cleanly.<br>
                - Tuned Outer Wall Acceleration: <strong>1000 - 1500 mm/s²</strong> and Outer Wall Speed: <strong>40 - 60 mm/s</strong> to eliminate vertical skirt ringing.
                </div>
                """,
                unsafe_allow_html=True
            )
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        # Run Pipeline Live
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 1. Coordinate Handoff (skips server geocoding)
        status_text.text("🔄 Locked in coordinates via handoff...")
        progress_bar.progress(15)
        
        lat, lon = st.session_state["selected_coords"]
        resolved_name = st.session_state["selected_address"]
        st.info(f"📍 **Target Location:** {resolved_name} (Coords: {lat:.6f}, {lon:.6f})")
            
        # 2. Parcel query
        parcel_info = None
        geometry_geojson = None
        if clip_to_parcel:
            status_text.text("🔄 Querying Connecticut CAMA & Parcel service...")
            progress_bar.progress(30)
            parcel_info = query_ct_parcel(lat, lon)
            
            if parcel_info:
                geometry_geojson = parcel_info["geometry"]
                st.success(
                    f"✓ **Parcel Boundary Found!**\n"
                    f"- Town: **{parcel_info['town']}**\n"
                    f"- Owner: **{parcel_info['owner']}**\n"
                    f"- Parcel ID: **{parcel_info['parcel_id']}**"
                )
            else:
                st.warning("⚠️ No parcel boundary found at this location (or address is outside CT). Falling back to rectangular tile.")
                clip_to_parcel = False
                
        # 3. Elevation download
        status_text.text("🔄 Downloading high-res LiDAR DEM samples...")
        progress_bar.progress(55)
        
        try:
            if geometry_geojson:
                poly_shape = shape(geometry_geojson)
                min_x, min_y, max_x, max_y = poly_shape.bounds
                width_ft = max_x - min_x
                resolution_feet = width_ft / resolution
                
                downloader = DEMDownloader(max_concurrency=5)
                grid_points = downloader.generate_parcel_grid(poly_shape.bounds, resolution_feet=resolution_feet)
                
                # PIP filter
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
                
                grid_elevations_ft = run_async_loop(downloader.download_elevations(points_2d_ft))
                points_2d = grid_elevations_ft[:, :2]
                elevations_m = grid_elevations_ft[:, 2] * 0.3048
                
                st.info(f"📥 Sampled **{len(points_2d)}** elevation points from UConn CT ECO LiDAR.")
            else:
                # Fallback USGS rectangular
                elevations, dx_m, dy_m = get_elevation_grid(lat, lon, width_m=200, height_m=200, resolution=resolution)
                st.info(f"📥 Sampled **{resolution}x{resolution}** grid from USGS EPQS.")
        except Exception as e:
            st.error(f"❌ Elevation Download Error: {e}")
            st.stop()
            
        # 4. Mesh Construction & Self-Repair Loop
        status_text.text("🔄 Triangulating 3D mesh & validating watertightness...")
        progress_bar.progress(80)
        
        attempt = 1
        max_repair_attempts = 3
        validated = False
        vertices = None
        faces = None
        
        if geometry_geojson:
            poly_shape = shape(geometry_geojson)
            min_x, min_y, max_x, max_y = poly_shape.bounds
            model_scale = model_width_mm / ((max_x - min_x) * 0.3048)
        else:
            model_scale = model_width_mm / 200.0
            
        while attempt <= max_repair_attempts:
            if geometry_geojson:
                thickness_meters = base_thickness_mm / (model_scale * z_exaggeration)
                builder = ManifoldMeshBuilder(geometry_geojson, thickness_meters=thickness_meters)
                vertices, faces = builder.build_mesh(points_2d, elevations_m, model_width_mm, z_exaggeration)
            else:
                south, north, west, east = calculate_grid_bounds(lat, lon, 200, 200)
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
                
            # Validate
            validation = validate_mesh(vertices, faces)
            if validation["valid"]:
                validated = True
                break
            else:
                # Try topological repair in-place via trimesh
                try:
                    import trimesh
                    import trimesh.repair as repair
                    st.info("🔄 Attempting automatic topological repair using Trimesh...")
                    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
                    repair.fill_holes(mesh)
                    repair.fix_winding(mesh)
                    repair.fix_normals(mesh)
                    repair.fix_inversion(mesh)
                    
                    if mesh.is_watertight and mesh.volume > 0:
                        vertices = mesh.vertices.astype(np.float32)
                        faces = mesh.faces.astype(np.int32)
                        # Re-run validation to get updated volume and success indicators
                        validation = validate_mesh(vertices, faces)
                        if validation["valid"]:
                            st.success("✅ Mesh successfully repaired topologically!")
                            validated = True
                            break
                except Exception as repair_err:
                    st.warning(f"⚠️ Automatic topological repair failed: {repair_err}")

                if attempt < max_repair_attempts:
                    base_thickness_mm += 1.0
                    st.warning(f"⚠️ Validation attempt {attempt} failed ({validation['errors']}). Auto-repair: increasing base thickness to {base_thickness_mm}mm and rebuilding...")
                    attempt += 1
                else:
                    st.error(f"❌ Mesh Validation Failed after {max_repair_attempts} attempts: {validation['errors']}")
                    st.warning("⚠️ **Proceeding with Non-Watertight Mesh**: The 3D model is shown below and can be downloaded, but it may contain open edges or non-manifold vertices.")
                    validated = True
                    break
                    
        # 5. Success outputs
        status_text.text("✓ Generation Complete!")
        progress_bar.progress(100)
        
        # Display Stats Card
        st.markdown(
            f"""
            <div class="glass-card">
                <div style="display: flex; justify-content: space-between; text-align: center;">
                    <div>
                        <div class="indicator-label">Mesh Watertight</div>
                        <div class="indicator-value">{"✅ Yes" if validation["watertight"] else "❌ No"}</div>
                    </div>
                    <div>
                        <div class="indicator-label">Total Faces</div>
                        <div class="indicator-value">{len(faces)}</div>
                    </div>
                    <div>
                        <div class="indicator-label">Model Volume</div>
                        <div class="indicator-value">{validation["volume"]:.1f} mm³</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # Display interactive 3D plot
        status_text.text("🎨 Rendering 3D interactive layout...")
        triangles = [
            (tuple(vertices[face[0]]), tuple(vertices[face[1]]), tuple(vertices[face[2]]))
            for face in faces
        ]
        
        polygon_coords_model = None
        if geometry_geojson:
            polygon_coords_model = []
            poly_shape = shape(geometry_geojson)
            X_scaled_all = (points_2d[:, 0] * 0.3048) * model_scale
            Y_scaled_all = (points_2d[:, 1] * 0.3048) * model_scale
            min_x_scaled = np.min(X_scaled_all)
            min_y_scaled = np.min(Y_scaled_all)
            
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
            
            first_ring = True
            for ring in rings:
                if not first_ring:
                    polygon_coords_model.append((None, None, None))
                first_ring = False
                for pt in ring:
                    x_ft, y_ft = pt[0], pt[1]
                    x_mm = x_ft * 0.3048 * model_scale
                    y_mm = y_ft * 0.3048 * model_scale
                    dists = np.hypot(points_2d[:, 0] - x_ft, points_2d[:, 1] - y_ft)
                    nearest_idx = np.argmin(dists)
                    z_mm = elevations_m[nearest_idx] * z_exaggeration * model_scale
                    x_mm -= min_x_scaled
                    y_mm -= min_y_scaled
                    polygon_coords_model.append((x_mm, y_mm, z_mm + 0.5))
                    
        # Generate Plotly figure object
        title = f"TopoTwin: {cleaned}"
        fig = create_plotly_visual(
            triangles=triangles,
            output_html="temp_output.html",
            title=title,
            polygon_coords=polygon_coords_model
        )
        
        # Render Plotly directly in Streamlit!
        st.plotly_chart(fig, use_container_width=True)
        
        # Binary STL download
        st.subheader("3. Export STL Model")
        
        # Generate STL in memory
        trimesh_mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
        stl_bytes = trimesh_mesh.export(file_type='stl')
        
        st.download_button(
            label="💾 Download .STL",
            data=stl_bytes,
            file_name=f"topo_{cleaned.replace(' ', '_').replace(',', '')}.stl",
            mime="application/sla",
            use_container_width=False
        )
        
        status_text.text("Generation completed successfully!")
        st.balloons()
