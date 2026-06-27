# Capstone Project Submission: TopoPlot (TopoTwin)

* **Selected Track**: Freestyle Track (Geospatial Agentic 3D Modeling)
* **Author**: Drew Jobson
* **Public Code Repository**: [https://github.com/drewjobson/TopoPlot](https://github.com/drewjobson/TopoPlot)
* **Video Demo**: [YouTube Video Link (5 Minutes or less)]

---

## 1. Executive Summary & Value Proposition

**TopoPlot (TopoTwin)** is an agentic geospatial CAD engine designed to automate the generation of watertight 3D terrain models clipped strictly to legal property boundaries. 

### The Problem
Architects, urban planners, and physical modelers require exact-scale representations of land plots for building design and 3D printing. However, existing GIS software requires manual georeferencing, coordinate system transformations, and clipping of contour lines in CAD. Traditional automated tools only produce flat rectangular blocks of terrain, which contain irrelevant adjacent properties and roads. Furthermore, legal property lines are highly complex, multi-part polygons (often featuring easements, nested holes, or disjoint islands) stored in municipal databases using winding orders and coordinate systems that trigger spatial query errors on the server.

### The Agentic Solution
TopoTwin solves this by wrapping a high-performance computational geometry engine in an autonomous, policy-gated agent harness. Users enter a physical address, and the agent automatically geocodes the coordinates, queries the legal municipal parcel boundaries, downloads bare-earth elevation data from high-resolution LiDAR services, constructs a 3D solid manifold shape, validates it for watertightness, and runs an automated self-repair loop to fix any topological defects. 

---

## 2. Technical Architecture & System Design

TopoTwin is designed as a modular system where the agent orchestrates external API tools while being constrained by a local security policy layer.

```
                  ┌─────────────────────────────────────┐
                  │          User Input Address         │
                  └──────────────────┬──────────────────┘
                                     ▼
                  ┌─────────────────────────────────────┐
                  │    Geocode Address (ArcGIS / OSM)   │
                  └──────────────────┬──────────────────┘
                                     ▼
                  ┌─────────────────────────────────────┐
                  │     Security & Compliance Gates     │
                  │  (Structural & Semantic Policies)   │
                  └──────────────────┬──────────────────┘
                                     ▼
                  ┌─────────────────────────────────────┐
                  │     CAMA GIS FeatureServer Query    │
                  │    (outSR: 2234 + 15m Query Buffer) │
                  └──────────────────┬──────────────────┘
                                     ▼
                  ┌─────────────────────────────────────┐
                  │   Filter & Distance Sort Parcels    │
                  │   (Resolve Centerline to Nearest)   │
                  └──────────────────┬──────────────────┘
                                     ▼
                  ┌─────────────────────────────────────┐
                  │  LiDAR DEM Fetch (State Plane 6434) │
                  └──────────────────┬──────────────────┘
                                     ▼
                  ┌─────────────────────────────────────┐
                  │    Delaunay Triangulation & CCW     │
                  │       Winding Order Correction      │
                  └──────────────────┬──────────────────┘
                                     ▼
                  ┌─────────────────────────────────────┐
                  │     Solid 3D Extrusion Generator    │
                  └──────────────────┬──────────────────┘
                                     ▼
                  ┌─────────────────────────────────────┐
                  │      Trimesh Validation Harness     │
                  │        (Self-Repair Loop < 3)       │
                  └──────────────────┬──────────────────┘
                                     ▼
                  ┌─────────────────────────────────────┐
                  │     Export Watertight STL/HTML      │
                  │     Trace to vibe_trajectory.jsonl  │
                  └─────────────────────────────────────┘
```

### Key Technical Integrations
1. **Planar Coordinate Handoff**: Coordinates are queried from the ArcGIS FeatureServer in `EPSG:2234` (Connecticut State Plane Feet) and locally transformed to `EPSG:6434` using `pyproj`. This prevents spatial indexing database errors on ArcGIS Online while preserving planar feet coordinates for physical mesh calculations.
2. **Esri JSON Winding Order Correction**: ArcGIS Online returns geometries with clockwise (CW) exterior rings and counter-clockwise (CCW) interior rings (holes), which is the reverse of OGC standards. We implement a parser utilizing the Shoelace formula to calculate signed areas, classify exterior shells and holes, and pass them to Shapely to preserve CCW winding order for the mesh faces.
3. **Multi-Part & Island Handling**: Disjoint properties (islands or utility easements) are parsed using `matplotlib.path.Path` codes (`MOVETO`, `LINETO`, `CLOSEPOLY`) to jump between disconnected boundaries without creating ghost triangles.
4. **Architectural Mode (1:1 Scale)**: Locks the vertical Z-exaggeration to exactly `1.0` so that vertical heights align with horizontal coordinates. This guarantees 100% physical accuracy for CAD building design.

---

## 3. Demonstration of Course Concepts

TopoTwin demonstrates three core design patterns covered in the Kaggle 5-Day AI Agents course:

### Concept 1: Structural & Semantic Gating (Day 4: Security & Policies)
The agent is wrapped in a strict policy engine (`harness/policy_server.py`) that implements two types of security gating:
* **Structural Gating**: Restricts access to execution tools (such as running shell commands via `raw_shell_execute`) based on user role (`viewer` vs. `admin`) and environment context (`production` vs. `development`).
* **Semantic Gating**: Inspects coordinate arguments before querying external elevation services. Any requests targeting restricted locations (e.g., Area 51 coordinates) are blocked, and the violation is logged.

### Concept 2: Validation-Driven Self-Repair Loop (Day 5: Production-Grade Reliability)
Triangulating organic boundaries can introduce overlapping facets, non-manifold vertices, or open edges.
* **The Harness**: The orchestrator pipes the generated mesh through a `trimesh` validator, checking for watertightness (zero boundary/open edges) and positive signed volume.
* **The Self-Repair Loop**: If the validation check fails, the agent intercepts the error message, dynamically increases the model's base thickness parameter to resolve intersecting perimeters, and rebuilds the mesh. The agent attempts this correction loop up to 3 times before falling back to a warning export.

### Concept 3: Trajectory & Telemetry Logging (Day 4: Observability)
Every intermediate step of the geocoding, parcel querying, elevation sampling, self-repair attempts, and validation outcomes is recorded in `vibe_trajectory.jsonl`. This matches OpenTelemetry tracing principles, giving developers and auditors a complete history of the agent's actions and reasoning.

---

## 4. Case Study: The Oxford Road Network Anomaly

During testing with the address `9 Hilltop Rd, Oxford, CT, 06478, USA`, we encountered a critical anomaly where the system generated a 3D model representing the road grid of the entire town of Oxford instead of a single plot of land.

### Diagnostic Findings
1. **Unregistered Address**: `9 Hilltop Rd` is not a registered municipal parcel (only 1, 2, 3, 6, and 8 Hilltop Road exist). The geocoder interpolated the location and placed the coordinates directly on the street centerline (Right-of-Way).
2. **Right-of-Way Intersection**: The spatial query matched the coordinates with the municipal Right-of-Way (ROW) parcel. In Oxford's CAMA GIS database, the road grid is represented as a single massive multi-polygon (62,780 points across 127 rings) covering all public roads.
3. **Database SRID Query Limits**: Attempting to buffer the query with `outSR: 6434` threw a `400 Bad Request` spatial reference database error, because the database spatial index did not support buffer distance operations on `6434`.

### Resolution Implementation
We resolved this by updating the FeatureServer query to return coordinates in `outSR: 2234` (fully supported for buffer queries). We implemented a distance-sorting filter inside the parcel service:
* The geocoded coordinate is projected to State Plane Feet.
* We loop through all returned parcels in a 15-meter buffer, filtering out any Right-of-Way features.
* We calculate the 2D Euclidean distance to all remaining candidate parcels, sorting them to select the closest valid residential plot (**`2 HILLTOP RD`**, owned by `CURRENT OWNER`, at a distance of **8.94 feet**).
* The resolved parcel geometry is locally projected to `6434` using `pyproj` to align with the UConn elevation downloader, successfully generating a clean, single-plot, watertight 3D solid mesh.

---

## 5. Verification & Test Metrics

We verified the final implementation against five separate benchmark properties to assert watertightness, positive signed volume, and security gating compliance:

| Address / Benchmark | Resolved Address / Entity | Points Fetched | Vertices | Watertight? | Signed Volume | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Clinton, CT (Flat/Hill)** | Bounding Box Bounding Area | N/A (Grid) | 1,596 | **True** | 48,082.43 mm³ | **PASS** |
| **Grand Canyon, AZ (Ravines)**| Bounding Box Bounding Area | N/A (Grid) | 1,596 | **True** | 101,718.96 mm³ | **PASS** |
| **Mount Rainier, WA (Peak)** | Bounding Box Bounding Area | N/A (Grid) | 1,596 | **True** | 271,178.82 mm³ | **PASS** |
| **242 E Main St, Clinton, CT**| 242 EAST MAIN ST #7 | 822 | 1,644 | **True** | 36,551.41 mm³ | **PASS** |
| **9 Hilltop Rd, Oxford, CT** | 2 HILLTOP RD | 151 | 302 | **True** | 19,717.92 mm³ | **PASS** |
| **Rogers Island, Branford, CT**| YON COMIS ISLAND/PHE | 866 | 1,730 | **True** | 29,350.87 mm³ | **PASS** |

### Security Evaluation Status
* **Structural Gating**: **PASS** (viewer roles blocked from command execution; admin roles allowed in development).
* **Semantic Gating**: **PASS** (queries targeting military installations like Area 51 successfully intercepted).
* **Self-Repair Loop**: **PASS** (Delaunay triangulation failures corrected in-place via Trimesh, validating watertightness).
