import streamlit as st
import numpy as np
import os
import asyncio
import trimesh
import json
import requests
import pandas as pd
from datetime import datetime
from shapely.geometry import shape, Polygon as ShapelyPolygon, MultiPolygon as ShapelyMultiPolygon
import io

from tools.geocoder import geocode_address, clean_address
from tools.parcel_service import query_ct_parcel
from tools.dem_downloader import DEMDownloader, get_elevation_grid, calculate_grid_bounds
from tools.mesh_builder import ManifoldMeshBuilder, build_solid_mesh, mesh_to_triangles
from tools.geometry_utils import build_polygon_outline_model_coords, parse_kml_geometry, parse_shapefile_zip
from harness.validator import validate_mesh
from visualizer import create_plotly_visual
from pipeline import TopoPlotPipeline, PipelineConfig

# ── Constants ──────────────────────────────────────────────────────────────────
DEFAULT_LOCATION = {
    "address": "500 Main St, Hartford, Connecticut, 06103",
    "coords": (41.76218, -72.67401),
    "query": "500 Main St, Hartford, CT",
}
CT_BOUNDS = {"lat_min": 40.98, "lat_max": 42.06, "lon_min": -73.73, "lon_max": -71.78}

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
    /* NOTE: Core theme colors (background, text, primary) are set in .streamlit/config.toml.
       Only custom element styles that config.toml cannot handle are kept here. */
    
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
        r = requests.get(url, params=params, timeout=4)
        if r.status_code == 200:
            return r.json().get("suggestions", [])
    except (requests.RequestException, ValueError, KeyError):
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
    except (requests.RequestException, ValueError, KeyError):
        pass
    return None

# Initialize Session States for Autocomplete Handoff
if "selected_address" not in st.session_state:
    st.session_state["selected_address"] = DEFAULT_LOCATION["address"]
if "selected_coords" not in st.session_state:
    st.session_state["selected_coords"] = DEFAULT_LOCATION["coords"]
if "search_query" not in st.session_state:
    st.session_state["search_query"] = DEFAULT_LOCATION["query"]
if "generation_history" not in st.session_state:
    st.session_state["generation_history"] = []

# App Header
st.markdown('<div class="gradient-title">🌟 TopoPlot 3D Terrain Generator</div>', unsafe_allow_html=True)
st.markdown('<div class="gradient-subtitle">Statewide Connecticut 2-Foot LiDAR Exact-Parcel Mesh Engine</div>', unsafe_allow_html=True)


# Tabs Layout
tab_generator, tab_guide = st.tabs([
    "🏔️ 3D Terrain Generator",
    "📖 User Guide & About"
])

with tab_generator:
    # Main two-column layout
    col_left, col_right = st.columns([1, 2], gap="large")

    with col_left:
        with st.container(border=True):
            st.subheader("1. Address Search")
        
            from streamlit_keyup import st_keyup
            address_input = st_keyup(
                "Search Connecticut Address (Autocomplete):",
                value=st.session_state["search_query"],
                debounce=400,
                key="address_keyup_input",
                help="Start typing any Connecticut address. Select the matching address from the dropdown list."
            )
        
            cleaned_query = clean_address(address_input)
        
            # Live Autocomplete Dropdown list — debounce by skipping if query matches selected address
            suggestions = []
            should_fetch = (
                len(cleaned_query) >= 3
                and cleaned_query.lower() != clean_address(st.session_state["selected_address"]).lower()
            )
            if should_fetch:
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
        
            # Check if address is in Connecticut
            lat, lon = st.session_state["selected_coords"]
            in_ct = (CT_BOUNDS["lat_min"] <= lat <= CT_BOUNDS["lat_max"]) and (CT_BOUNDS["lon_min"] <= lon <= CT_BOUNDS["lon_max"])
            if not in_ct:
                st.warning("⚠️ **Out-of-State Location**: This address is outside Connecticut. Exact parcel boundary clipping is unavailable. A standard 200m x 200m rectangular terrain tile will be generated using USGS elevation data.")
            
            # 2D Map Preview of Selected Location
            map_data = pd.DataFrame([{"lat": lat, "lon": lon}])
            st.map(map_data, zoom=14, use_container_width=True)
        
            # Custom Boundary Uploader (GeoJSON, KML, Shapefile ZIP)
            st.markdown("---")
            st.markdown("**📂 Upload Custom Site Boundary:**")
            uploaded_boundary = st.file_uploader(
                "Upload boundary file:",
                type=["geojson", "json", "kml", "zip"],
                help="Upload a GeoJSON, KML, or zipped Shapefile boundary. This overrides address search and clips the 3D model to your custom polygon."
            )
        
            if uploaded_boundary is not None:
                try:
                    file_name = uploaded_boundary.name.lower()
                    geom = None
                
                    if file_name.endswith(".kml"):
                        # Parse KML with built-in xml.etree
                        raw_bytes = uploaded_boundary.read()
                        geom = parse_kml_geometry(raw_bytes)
                        if geom is None:
                            st.error("❌ No Polygon found in KML file.")
                    elif file_name.endswith(".zip"):
                        # Parse zipped Shapefile with pyshp
                        raw_bytes = uploaded_boundary.read()
                        try:
                            geom = parse_shapefile_zip(raw_bytes)
                        except ImportError as ie:
                            st.error(f"❌ {ie}")
                        if geom is None:
                            st.error("❌ No Polygon found in Shapefile ZIP.")
                    else:
                        # GeoJSON / JSON
                        geojson_data = json.load(uploaded_boundary)
                        if geojson_data.get("type") == "FeatureCollection":
                            features = geojson_data.get("features", [])
                            if features:
                                geom = features[0].get("geometry")
                        elif geojson_data.get("type") == "Feature":
                            geom = geojson_data.get("geometry")
                        else:
                            geom = geojson_data
                
                    if geom and geom.get("type") in ["Polygon", "MultiPolygon"]:
                        poly_shape = shape(geom)
                        centroid = poly_shape.centroid
                    
                        st.session_state["selected_coords"] = (centroid.y, centroid.x)
                        st.session_state["selected_address"] = "Custom Uploaded Boundary"
                        st.session_state["custom_geometry"] = geom
                        st.success(f"✅ Valid boundary loaded from `{uploaded_boundary.name}`!")
                    elif geom is not None:
                        st.error("❌ Invalid geometry: No Polygon or MultiPolygon found.")
                except Exception as e:
                    st.error(f"❌ Failed to parse boundary file: {e}")
            else:
                if "custom_geometry" in st.session_state:
                    del st.session_state["custom_geometry"]
            
            st.markdown("**Try these municipal examples:**")
            col_ex1, col_ex2 = st.columns(2)
            with col_ex1:
                if st.button("Hartford Public Library"):
                    st.session_state["selected_address"] = DEFAULT_LOCATION["address"]
                    st.session_state["selected_coords"] = DEFAULT_LOCATION["coords"]
                    st.session_state["search_query"] = DEFAULT_LOCATION["query"]
                    st.rerun()
            with col_ex2:
                if st.button("CT State Capitol"):
                    st.session_state["selected_address"] = "210 Capitol Ave, Hartford, Connecticut, 06106"
                    st.session_state["selected_coords"] = (41.76428, -72.68232)
                    st.session_state["search_query"] = "210 Capitol Ave, Hartford, CT"
                    st.rerun()

        # Spacing between containers
        st.write("")

        with st.container(border=True):
            st.subheader("2. Model & Fidelity Settings")
        
            architect_mode = st.toggle(
                "Architectural Mode (1:1 Realistic Scale)",
                value=False,
                help="Lock vertical elevation scale to match horizontal scale exactly (1:1). This is crucial for architects importing the STL model into CAD software for building design."
            )
        
            with st.expander("⚙️ Advanced Print Settings", expanded=False):
                resolution = st.slider(
                    "Grid Resolution (Fidelity):",
                    min_value=15,
                    max_value=120,
                    value=45,
                    step=5,
                    help="Higher values increase triangle density (fidelity) for architects but increase DEM sampling duration."
                )
            
                if architect_mode:
                    z_exaggeration = 1.0
                    st.info("ℹ️ **Z-Exaggeration locked to 1.0** for realistic 1:1 scale.")
                else:
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
                    st.toast(f"Print width {model_width_mm:.0f}mm exceeds Creality K1 build volume (220mm)", icon="⚠️")
                
                clip_to_parcel = st.checkbox(
                    "Clip strictly to Legal Parcel Boundaries",
                    value=True,
                    help="Uncheck to generate a standard rectangular terrain tile instead."
                )
            
            generate_btn = st.button("Generate 3D Model", type="primary", use_container_width=True)

    with col_right:
        if not generate_btn and "mesh_vertices" not in st.session_state:
            with st.container(border=True):
                st.markdown("<div style='text-align: center; padding: 40px 20px;'>", unsafe_allow_html=True)
                st.markdown("<div style='font-size: 5rem; line-height: 1;'>🏔️</div>", unsafe_allow_html=True)
                st.markdown("<h3 style='margin-top: 20px; color: #1F2937;'>Ready to Generate</h3>", unsafe_allow_html=True)
                st.markdown("<p style='color: #4B5563;'>Configure your settings on the left and click <strong>Generate 3D Model</strong> to fetch Connecticut ImageServer LiDAR data and build a watertight STL terrain mesh.</p>", unsafe_allow_html=True)
                st.markdown(
                    """
                    <div style="background: rgba(230, 81, 0, 0.05); border: 1px solid rgba(230, 81, 0, 0.15); border-radius: 8px; padding: 16px; text-align: left; margin-top: 24px; color: #1F2937;">
                    <strong>⚙️ 3D Slicer Kinematics Recommendations:</strong><br>
                    - Use the <strong>Arachne</strong> wall generator in your slicer to fill fine property edges cleanly.<br>
                    - Tuned Outer Wall Acceleration: <strong>1000 - 1500 mm/s²</strong> and Outer Wall Speed: <strong>40 - 60 mm/s</strong> on high-speed printers to eliminate vertical skirt ringing.
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            if generate_btn:
                # Run Pipeline with st.status loading widget
                with st.status("Generating 3D Model...", expanded=True) as status_widget:
                    # Check if the user typed a new address but did not click a suggestion
                    typed_differs = (
                        clean_address(address_input).lower() != clean_address(st.session_state["selected_address"]).lower()
                    )
                    has_custom_geom = st.session_state.get("custom_geometry") is not None
                    
                    if typed_differs and not has_custom_geom:
                        st.write("🔄 Resolving coordinates for new search query...")
                        lat = None
                        lon = None
                        resolved_name = address_input
                    else:
                        st.write("🔄 Locked in coordinates via handoff...")
                        lat, lon = st.session_state["selected_coords"]
                        resolved_name = st.session_state["selected_address"]
                    
                    cleaned = clean_address(resolved_name)
                    if lat is not None and lon is not None:
                        st.write(f"📍 **Target:** {resolved_name} ({lat:.6f}, {lon:.6f})")
                    else:
                        st.write(f"📍 **Target Address:** {resolved_name}")

                    # Create TopoPlotPipeline
                    config = PipelineConfig(
                        lat=lat,
                        lon=lon,
                        address=resolved_name,
                        clip_to_parcel=clip_to_parcel,
                        resolution=resolution,
                        base_thickness_mm=base_thickness_mm,
                        z_exaggeration=z_exaggeration,
                        model_width_mm=model_width_mm,
                        custom_geometry=st.session_state.get("custom_geometry")
                    )

                    # Set up UI status callbacks inside st.status
                    def on_status(step, status_type, message):
                        if status_type == "info":
                            st.write(f"🔄 {message}")
                        elif status_type == "success":
                            st.write(f"✅ {message}")
                        elif status_type == "warning":
                            st.write(f"⚠️ {message}")
                        elif status_type == "error":
                            st.write(f"❌ {message}")

                    pipeline = TopoPlotPipeline(config, on_status=on_status)
                    result = pipeline.run()

                    if not result.success:
                        status_widget.update(label="❌ Generation Failed", state="error", expanded=True)
                        st.error(f"❌ Generation failed: {result.error_msg}")
                        st.stop()

                    vertices = result.vertices
                    faces = result.faces
                    validation = result.validation
                    parcel_info = result.parcel_info
                    points_2d = result.points_2d
                    elevations_m = result.elevations_m
                    model_scale = result.model_scale
                    geometry_geojson = parcel_info.get("geometry") if parcel_info else None

                    if geometry_geojson and parcel_info.get("owner") != "Unknown":
                        st.write(
                            f"✓ **Parcel Found:** {parcel_info['town']} — Owner: {parcel_info['owner']} (ID: {parcel_info['parcel_id']})"
                        )

                    # Update session state if geocoding was resolved inside the pipeline dynamically
                    if result.lat is not None and result.lon is not None:
                        st.session_state["selected_coords"] = (result.lat, result.lon)
                        resolved_addr_new = parcel_info.get("address", result.parcel_info.get("address", resolved_name))
                        st.session_state["selected_address"] = resolved_addr_new
                        st.session_state["search_query"] = resolved_addr_new
                        resolved_name = resolved_addr_new
                        cleaned = clean_address(resolved_name)

                    status_widget.update(label="✅ Generation Complete!", state="complete", expanded=False)
            
                # Store in session state for rerun persistence
                st.session_state["mesh_vertices"] = vertices
                st.session_state["mesh_faces"] = faces
                st.session_state["mesh_validation"] = validation
                st.session_state["mesh_parcel_info"] = parcel_info
                st.session_state["mesh_points_2d"] = points_2d
                st.session_state["mesh_elevations_m"] = elevations_m
                st.session_state["mesh_model_scale"] = model_scale
                st.session_state["mesh_geometry_geojson"] = geometry_geojson
                st.session_state["mesh_cleaned_address"] = cleaned
            
                # Append to generation history
                trimesh_mesh_hist = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
                stl_bytes_hist = trimesh_mesh_hist.export(file_type='stl')
                st.session_state["generation_history"].append({
                    "address": resolved_name,
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "faces": len(faces),
                    "volume": validation.get("volume", 0.0),
                    "stl_bytes": stl_bytes_hist,
                    "cleaned": cleaned,
                })
            else:
                # Retrieve from session state
                vertices = st.session_state["mesh_vertices"]
                faces = st.session_state["mesh_faces"]
                validation = st.session_state["mesh_validation"]
                parcel_info = st.session_state["mesh_parcel_info"]
                points_2d = st.session_state["mesh_points_2d"]
                elevations_m = st.session_state["mesh_elevations_m"]
                model_scale = st.session_state["mesh_model_scale"]
                geometry_geojson = st.session_state["mesh_geometry_geojson"]
                cleaned = st.session_state["mesh_cleaned_address"]
        
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
        
            # Visualization settings controls
            col_vis1, col_vis2 = st.columns(2)
            with col_vis1:
                render_style = st.selectbox(
                    "3D Rendering Style:",
                    options=["Solid", "Wireframe", "Solid + Wireframe", "Solid + Contours"],
                    index=0,
                    help="Choose how the 3D model is rendered in the viewer."
                )
            with col_vis2:
                color_scheme = st.selectbox(
                    "Elevation Color Scheme:",
                    options=["Earth", "Viridis", "Terrain", "Portland", "Gray", "Hot"],
                    index=0,
                    help="Select the colorscale used to map vertex elevations."
                )
            
            # Display interactive 3D plot
            triangles = mesh_to_triangles(vertices, faces)
        
            # Build polygon outline using shared utility
            polygon_coords_model = None
            if geometry_geojson and points_2d is not None and elevations_m is not None:
                polygon_coords_model = build_polygon_outline_model_coords(
                    geometry_geojson, points_2d, elevations_m, model_scale, z_exaggeration
                )
                    
            # Generate Plotly figure object
            title = f"TopoTwin: {cleaned}"
            fig = create_plotly_visual(
                triangles=triangles,
                output_html="temp_output.html",
                title=title,
                polygon_coords=polygon_coords_model,
                colorscale=color_scheme,
                render_mode=render_style
            )
        
            # Render Plotly directly in Streamlit!
            st.plotly_chart(fig, use_container_width=True)
        
            # Export options
            st.subheader("3. Export & Download 3D Model")
        
            export_format = st.selectbox(
                "Select 3D File Format:",
                options=["STL (3D Printing / CAD)", "OBJ (Wavefront)", "PLY (with Elevation Vertex Colors)", "3MF (3D Manufacturing Format)"],
                index=0,
                help="Select the file format to export the generated 3D mesh model."
            )
        
            # Generate model in memory
            trimesh_mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        
            if "PLY" in export_format:
                # Map Z elevation to colors
                z_vals = vertices[:, 2]
                z_min, z_max = np.min(z_vals), np.max(z_vals)
                if z_max > z_min:
                    normalized_z = (z_vals - z_min) / (z_max - z_min)
                else:
                    normalized_z = np.zeros_like(z_vals)
                
                colors = np.zeros((len(vertices), 4), dtype=np.uint8)
                for idx, nz in enumerate(normalized_z):
                    if nz < 0.5:
                        t = nz / 0.5
                        r = int(34 + t * (139 - 34))
                        g = int(139 + t * (90 - 139))
                        b = int(34 + t * (43 - 34))
                    else:
                        t = (nz - 0.5) / 0.5
                        r = int(139 + t * (255 - 139))
                        g = int(90 + t * (255 - 90))
                        b = int(43 + t * (255 - 43))
                    colors[idx] = [r, g, b, 255]
                
                trimesh_mesh.visual.vertex_colors = colors

            if "STL" in export_format:
                file_extension = "stl"
                mime_type = "application/sla"
                export_bytes = trimesh_mesh.export(file_type='stl')
                label_text = "💾 Download .STL"
            elif "OBJ" in export_format:
                file_extension = "obj"
                mime_type = "text/plain"
                export_bytes = trimesh_mesh.export(file_type='obj')
                label_text = "💾 Download .OBJ"
            elif "PLY" in export_format:
                file_extension = "ply"
                mime_type = "application/octet-stream"
                export_bytes = trimesh_mesh.export(file_type='ply')
                label_text = "💾 Download .PLY"
            elif "3MF" in export_format:
                file_extension = "3mf"
                mime_type = "application/octet-stream"
                export_bytes = trimesh_mesh.export(file_type='3mf')
                label_text = "💾 Download .3MF"
            
            st.download_button(
                label=label_text,
                data=export_bytes,
                file_name=f"topo_{cleaned.replace(' ', '_').replace(',', '')}.{file_extension}",
                mime=mime_type,
                use_container_width=False
            )


with tab_guide:
    st.header("📖 TopoPlot User Guide & About")
    st.markdown(
        """
        ### 🏔️ About TopoTwin
        **TopoTwin (TopoPlot)** is a professional-grade 3D terrain and property boundary mesh generation engine. 
        It integrates Connecticut tax assessor geographic databases (CAMA/Parcel services) with bare-earth LiDAR 
        digital elevation models (DEMs) to construct watertight, physically accurate 3D solid meshes (.STL, .OBJ, .PLY, .3MF) 
        ready for immediate 3D printing or CAD import.
        
        ---
        
        ### 🚀 How to Use
        1. **Address Search**: Enter any Connecticut address in the search box. The real-time autocomplete will provide matching suggestions. Clicking a suggestion locks in the property centroid.
        2. **Custom Site Boundary**: Optionally upload your own `.geojson`, `.kml`, or `.zip` Shapefile containing a Polygon boundary. This overrides the address search and clips the terrain exactly to your boundary.
        3. **Print Customization**:
           - **Architectural Mode**: Toggling this mode disables arbitrary vertical scaling and locks the Z-exaggeration to exactly `1.0`. This ensures a true 1:1 physical representation.
           - **Resolution**: Adjust the slider to set the number of grid points sampled across the property. Higher values capture finer terrain details but take longer to process.
           - **Exaggeration**: Amplify vertical elevation features (slopes, ravines, peaks) for artistic or visual clarity.
           - **Base Thickness**: Set the thickness of the flat printed base in millimeters.
        4. **Visualization Controls**: Toggle between **Solid**, **Wireframe**, and **Contours** styles, and customize the color scheme in real time.
        5. **Download Model**: Select your preferred export format and click the download button.
        """
    )
    
    st.subheader("🎓 Capstone Evaluator Q&A")
    with st.expander("❓ Q1: What is the architectural design (Model + Harness) of this project?"):
        st.markdown(
            """
            This project follows the core paradigm taught in the 5-day course: **Agent = Model + Harness**. 
            Rather than relying on a raw generative model to write code in a vacuum, TopoPlot wraps the agent's code generation 
            and execution in a strict validation-driven harness:
            1. **Validation Engine (`harness/run_evals.py`)**: Asserts watertight geometry, correct coordinate systems, and positive signed volumes.
            2. **Gated Execution (`harness/policy_server.py`)**: Role-based access controls verify tool execution permissions and semantic coordinates (blocking queries to sensitive areas like Area 51) before making requests.
            3. **Asynchronous Trajectory Tracing**: Every geocoding call, parcel query, and repair step logs to a structured trajectory file (`vibe_trajectory.jsonl`).
            """
        )
    with st.expander("❓ Q2: How does the watertight validation and self-repair loop function?"):
        st.markdown(
            """
            When Delaunay triangulation or extrusion produces non-watertight meshes (e.g. open boundaries or non-manifold edges), the system triggers a **Self-Repair Loop**:
            - It applies topological repairs (fixing face normals, filling holes, and correcting winding orders) in-place using `trimesh.repair`.
            - If validation still fails, the system automatically increases the base thickness in 1mm steps and retries up to 3 times to ensure a watertight solid manifold.
            """
        )
    with st.expander("❓ Q3: How does the uploader handle out-of-state clipping?"):
        st.markdown(
            """
            Inside Connecticut, the uploader projects coordinates to the State Plane system (`EPSG:6434` feet) and queries the high-resolution UConn LiDAR server. 
            Outside Connecticut, it dynamically projects the upload to Web Mercator (`EPSG:3857` meters), generates the grid, projects back to WGS84 Lat/Lon to query USGS EPQS concurrently, and builds the mesh using metric units. This ensures custom boundary clipping works globally.
            """
        )
    with st.expander("❓ Q4: What are the 3D printing and slicer recommendations?"):
        st.markdown(
            """
            Exact-boundary terrain models feature highly irregular edges. To print them cleanly:
            - **Arachne Wall Generator**: Select the Arachne engine instead of Classic in your slicer to dynamically vary extrusion widths and fill fine property corners.
            - **Skirt Ringing Prevention**: Reduce outer wall speed to 40-60 mm/s and outer wall acceleration to 1000-1500 mm/s² on high-speed printers to eliminate mechanical ringing along the vertical base skirt.
            """
        )


# ── Generation History Sidebar ──────────────────────────────────────────────────
with st.sidebar:
    st.subheader("📋 Generation History")
    history = st.session_state.get("generation_history", [])
    if not history:
        st.caption("No models generated yet.")
    else:
        for i, entry in enumerate(reversed(history)):
            with st.expander(f"📍 {entry['address'][:30]}… — {entry['time']}", expanded=(i == 0)):
                st.write(f"**Faces:** {entry['faces']:,}")
                st.write(f"**Volume:** {entry['volume']:,.1f} mm³")
                st.download_button(
                    "💾 Re-download .STL",
                    data=entry["stl_bytes"],
                    file_name=f"topo_{entry['cleaned'].replace(' ', '_').replace(',', '')}.stl",
                    mime="application/sla",
                    key=f"hist_dl_{i}",
                )
