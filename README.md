# TopoPlot: Advanced 3D Terrain & Exact-Parcel Mesh Generator

**TopoPlot (TopoTwin)** is an advanced geospatial 3D mesh engine designed for architectural site analysis and 3D printing. Unlike traditional rectangular bounding-box terrain models, TopoPlot geocodes a target address, queries legal property parcel boundaries, fetches high-resolution LiDAR bare-earth DEMs, and constructs a mathematically watertight 3D solid manifold shaped precisely like the property parcel.

---

## Features

- **Exact-Boundary Extrusion**: Triangulates and clips the terrain mesh strictly to the legal property parcel boundaries, eliminating geometric redundancy for 3D printing and CAD modeling.
- **High-Resolution Elevation Source**: Pulls from the **UConn CT ECO 2023 2-Foot LiDAR Elevation ImageServer** `/getSamples` endpoint in Connecticut, falling back to the **USGS EPQS** for out-of-state addresses.
- **Planar Coordinate Handoff (`outSR: 6434`)**: Queries parcel boundaries directly in Connecticut State Plane Feet, offloading geodetic-to-planar projection to the ArcGIS Online FeatureServer backend.
- **Esri JSON Winding Order Correction**: Dynamically parses flat Esri JSON ring arrays, classifying exterior and interior (hole/easement) rings using the Shoelace formula to construct standard OGC-compliant CCW winding order polygons in Shapely.
- **Multi-Part & Island Handling**: Leverages `matplotlib.path.Path` codes (`MOVETO` / `LINETO` / `CLOSEPOLY`) to handle disconnected parcel polygons and holes cleanly without ghost triangles or lines.
- **Watertight Manifold Validation**: Uses `trimesh` to perform watertightness checks (manifold structure with zero boundary/open edges) and positive signed volume checks.
- **Physical Model Scaling**: XY coordinates are shifted to minimum bounds `(0, 0)` for CAD file compatibility, while Z heights remain relative to sea level for accurate topological reference.

---

## Technical Architecture

```
Address/Coords ──> Geocode Address (Nominatim)
                       │
                       ▼
            Query CT CAMA FeatureServer (outSR: 6434)
                       │
                       ▼
         Generate Point Grid & Fetch UConn LiDAR DEM
                       │
                       ▼
           2D SciPy Delaunay Triangulation
                       │
                       ▼
       Vectorized Centroid Point-in-Polygon Filtering
                       │
                       ▼
      Watertight Solid Extrusion (CCW Top/CW Base/CCW Skirt)
                       │
                       ▼
       Trimesh Geometric Integrity Validation
                       │
                       ▼
        Export Binary STL & Interactive Plotly HTML
```

---

## 3D Slicer Kinematics Recommendations (OrcaSlicer & Creality K1)

Exact-boundary parcel meshes feature highly irregular perimeters. Printing these perimeters requires specific slicer adjustments to prevent mechanical ringing and extrusion voids:

- **Arachne Wall Generator**: In **OrcaSlicer**, select the **Arachne** wall generator instead of Classic. Arachne dynamically varies extrusion width to fill thin, sharp property corners, eliminating voids and preserving fine boundary details.
- **Outer Wall Speed & Acceleration (Creality K1)**:
  - Set **Outer wall acceleration** to **1000 - 1500 mm/s²** (down from the default 5000 mm/s²).
  - Reduce **Outer wall speed** to **40 - 60 mm/s**.
  - Ensure **Input Shaper** is calibrated on both X and Y axes to dampen resonances.

---

## Installation & Setup

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/drewjobson/TopoPlot.git
   cd TopoPlot
   ```

2. **Set up Virtual Environment**:
   ```bash
   python -m venv .venv
   # Windows:
   .\.venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## Usage

### Generate Clipped Parcel Mesh
Generate a 3D physical model of 242 East Main Street, Clinton, CT at 40x40 grid resolution:
```bash
python topo_agent.py "242 East Main Street, Clinton, CT" --resolution 40 --output-stl clinton_town_hall.stl --output-html clinton_town_hall.html
```

### Generate Rectangular Bounding-Box Mesh
Disable boundary clipping and output a standard rectangular terrain tile:
```bash
python topo_agent.py "242 East Main Street, Clinton, CT" --resolution 40 --no-clip --output-stl clinton_square.stl --output-html clinton_square.html
```

### Run the Evaluation & Validation Suite
```bash
python harness/run_evals.py
```
