# Walkthrough: TopoTwin Exact-Boundary 3D Mesh Generator

We have completed the exact-boundary 3D terrain mesh generation pipeline with Connecticut CAMA/Parcel integration, UConn high-resolution LiDAR bare-earth DEM downloads, robust spatial querying, and real-time visualization enhancements.

---

## 🔍 Case Study: The Oxford Road Network Anomaly (9 Hilltop Rd)

When trying to model `9 Hilltop Rd, Oxford, CT, 06478, USA`, the engine previously generated a 3D model of the entire road network of Oxford instead of a single plot of land. 

### What Happened?
1. **Unregistered Parcel Geocoding**: `9 Hilltop Rd` does not legally exist in the Oxford tax assessor database (only 1, 2, 3, 6, and 8 Hilltop Road exist). Because of this, the geocoder interpolated the location and placed the coordinate point (`Lat 41.438698, Lon -73.094791`) directly on the street centerline (Right-of-Way).
2. **Right-of-Way Intersection**: The database query searched for the parcel containing this point. Because the coordinate was on the street centerline, it intersected the town's **Right-of-Way (ROW)** parcel.
3. **Massive Road Network Multi-Polygon**: In many Connecticut towns, the municipal road grid is represented as a single, massive multi-polygon (in Oxford's case, containing over 62,000 vertices across 127 rings). The engine returned this entire road network parcel, leading the mesh builder to construct a 3D model of all roads in Oxford.
4. **ArcGIS SQL Query Limits**: A 15-meter buffer search was previously attempted to find adjacent parcels, but requesting the geometry in EPSG:6434 (`outSR=6434`) combined with distance/units parameters failed with a database SQL error (`400 Bad Request: The spatial reference identifier (SRID) is not valid`). The FeatureServer database spatial indices did not support buffer queries projected to `6434`.

---

### How We Fixed It
We updated [tools/parcel_service.py](tools/parcel_service.py) with the following robust resolution logic:

1. **SRID Query Correction**: We changed the ArcGIS FeatureServer output projection query parameter to `"outSR": "2234"`. EPSG:2234 is fully registered in the GIS database's spatial index, allowing the distance-buffered query to execute successfully without SQL errors.
2. **Distance-Based Sorting**: We project the geocoded query coordinate to Connecticut State Plane Feet (`EPSG:6434`). For each candidate parcel returned in the buffer zone:
   - We check if it is a municipal road network (`Parcel_Typ == "ROW"`, `Parcel_ID == "ROW"`, or owner/location names containing "RIGHT-OF-WAY", "RIGHT OF WAY", or "TOWN ROAD"). If so, we skip it.
   - For valid residential properties, we parse their geometry (handling both Esri JSON rings and GeoJSON) and project them from `2234` to `6434` using `pyproj`.
   - We calculate the 2D Euclidean distance from the query point to the parcel boundary.
   - We sort all candidate parcels and select the **closest** valid residential parcel.
3. **Local Projection**: The final resolved geometry is converted and returned in `EPSG:6434`, ensuring seamless alignment with the UConn DEM LiDAR elevation downloader.

---

## Key Technical Implementations

### 1. Unified Shared Pipeline (`pipeline.py`)
All core workflow steps (coordinate geocoding, parcel queries, elevation downloads, mesh building, self-repair loops, and caching) have been consolidated into a single class `TopoPlotPipeline` in [pipeline.py](pipeline.py).
- Both `app.py` and `topo_agent.py` call this unified pipeline, eliminating code duplication.
- Dynamic caching hooks adaptively wrap data-fetching functions with Streamlit's `@st.cache_data` when running inside the Streamlit runtime, falling back to a raw memory cache for CLI scripts.

### 2. Streamlit Session State & Persistence (`app.py`)
- We implemented cache persistence for generated meshes in `st.session_state`.
- Adjusting sidebar parameters or visualization styling causes Streamlit to rerun, but the app instantly retrieves the mesh from session state to redraw the visualizer without repeating the expensive LiDAR downloads.

### 3. Real-Time 3D Rendering Styles & Colorscales
- We added dropdown selectors directly above the 3D visualizer.
- **3D Rendering Styles**: Users can switch between **Solid**, **Wireframe**, **Solid + Wireframe**, and **Solid + Contours**.
- **Contour Slicing**: A custom intersection algorithm extracts horizontal slices of the 3D mesh at fixed elevation intervals and renders them in a single Scatter3D trace.
- **Colorscale Schemes**: Dropdown options map the elevation values to schemes like **Earth**, **Viridis**, **Terrain**, **Portland**, **Gray**, or **Hot**.

### 4. Custom Boundary Upload & Projection
- Added a **Custom Boundary Uploader** in the sidebar that supports **GeoJSON/JSON**, **KML**, and **zipped Shapefiles**.
  - **KML parsing** is done with Python's built-in `xml.etree.ElementTree` to keep dependencies clean.
  - **Shapefile parsing** uses the pure-Python `pyshp` package to read shapefiles inside a zip archive without heavy compiled binary libraries.
- If a custom geometry is uploaded:
  - If the centroid is inside Connecticut, it projects the polygon to `EPSG:6434` feet and pulls from high-resolution UConn LiDAR.
  - If outside Connecticut, it projects the polygon to `EPSG:3857` (Web Mercator meters), generates the grid, queries USGS EPQS concurrently, and builds the mesh using metric units. This extends custom boundary clipping globally!

### 5. Multi-Format Exporters
- Dropdown selector allows exporting the mesh into:
  - **STL** (3D printing/CAD)
  - **OBJ** (Wavefront OBJ)
  - **3MF** (3D Manufacturing Format)
  - **PLY (with vertex colors)**: Automatically interpolates vertex elevations along a terrain gradient (Green -> Brown -> White) and exports vertex-colored PLY meshes for immediate render mockups in Blender.

### 6. Shared Geometry Utilities (`tools/geometry_utils.py`)
- Extracted `build_polygon_outline_model_coords()` to centralize the projection of 3D outlines in model-space. Both `app.py` and `topo_agent.py` now call this utility.
- Added KML and Shapefile ZIP parsers to keep parsing logic modular and clean.

### 7. Narrower Exception Handling & Defensive Quality
- Updated broad exception blocks in `tools/geocoder.py` and `tools/dem_downloader.py` to catch specific request errors (`requests.RequestException`, `aiohttp.ClientError`, `KeyError`, etc.) and log failure context defensively.
- Cleaned up duplicate inline imports and the `sys.path` append hacks.

---

## 3D Slicer Kinematics Recommendations (OrcaSlicer & Creality K1)

Exact-boundary parcel meshes feature organic, irregular perimeters. Printing these boundaries introduces specific mechanical variables.

> [!TIP]
> **Arachne Wall Generator**
> - In **OrcaSlicer**, select the **Arachne** wall generator instead of Classic. Arachne dynamically varies extrusion width to fill thin, sharp property corners, eliminating voids and preserving fine boundary details.

> [!IMPORTANT]
> **Outer Wall Acceleration Tuning for Creality K1**
> - Irregular boundaries involve rapid toolpath direction changes. To prevent mechanical ringing/ghosting along the vertical skirt walls of the mesh on the **Creality K1**:
>   1. Set **Outer wall acceleration** to **1000 - 1500 mm/s²** (down from the default 5000 mm/s²).
>   2. Reduce **Outer wall speed** to **40 - 60 mm/s**.
>   3. Ensure **Input Shaper** is calibrated on both X and Y axes to dampen resonances.

---

## Verification Metrics: 2 Hilltop Road, Oxford, CT

We ran the completed pipeline for `9 Hilltop Rd, Oxford, CT` (resolving to `2 HILLTOP RD`, resolution: 20):
*   **Geocode**: Lat 41.43870, Lon -73.09479
*   **Resolved Address**: 2 HILLTOP RD, Oxford, CT
*   **DEM Source**: UConn CT ECO 2023 2-Foot LiDAR ImageServer
*   **Elevation Points**: 151 points fetched concurrently
*   **Unique Vertices**: 302 unique vertices
*   **Harness Validation**: Passed!
    *   Watertight manifold: **True** (0 boundary/open edges, 0 non-manifold edges)
    *   Signed Volume: **Positive** (19,717.92 cubic mm)
*   **Outputs**:
    *   `oxford_2_hilltop_road.stl` (Watertight 3D solid parcel mesh)
    *   `oxford_2_hilltop_road.html` (Plotly visualizer with multi-part outline)

---

## How to Execute

### CLI Run
```powershell
.\.venv\Scripts\python.exe topo_agent.py "9 Hilltop Rd, Oxford, CT, 06478, USA" --resolution 20 --output-stl oxford_2_hilltop_road.stl --output-html oxford_2_hilltop_road.html
```

### Run Evaluation Suite
```powershell
.\.venv\Scripts\python.exe harness/run_evals.py
```

### Run Interactive Web Application
```powershell
.\.venv\Scripts\streamlit run app.py
```
