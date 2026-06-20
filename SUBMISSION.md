# Capstone Project Submission: TopoPlot (TopoTwin)

## Project Overview

**TopoPlot (TopoTwin)** is an agentic 3D terrain and exact-parcel mesh generator designed for architectural planning and physical 3D printing. It showcases key advanced agentic capabilities including **policy-driven gating (security/compliance)**, **validation-driven self-repair (reliability)**, and **advanced API orchestration**.

Instead of producing generic rectangular terrain blocks, TopoPlot geocodes physical addresses, queries legal municipal parcel boundaries from the ArcGIS Online FeatureServer, downloads raw elevation points concurrently from the high-resolution UConn CT ECO 2023 2-Foot LiDAR ImageServer, and builds a watertight 3D manifold printed strictly inside the property's legal boundaries.

---

## Key Agentic Capabilities Demonstrated

### 1. Structural and Semantic Gating (Security & Policy Enforcement)
To prevent unauthorized API access and queries in sensitive locations, the agent incorporates a policy layer:
* **Structural Gating**: Verifies user roles and execution environments (localhost vs. production) before allowing system command execution (`raw_shell_execute`) or system environment changes, blocking administrative commands for viewer roles in production.
* **Semantic Gating**: Inspects coordinate parameters before querying USGS/CT ECO elevation servers. For example, queries targeting restricted military zones (e.g., Area 51 coordinates) are intercepted and rejected, returning a security violation trace.

### 2. Validation-Driven Self-Repair Loop (Reliability)
Computational geometry operations (such as SciPy Delaunay triangulation and extrusion of organic boundaries) can occasionally fail watertightness constraints or return negative volumes due to narrow boundary perimeters.
* **Validation Harness**: The orchestrator pipes the generated mesh through a `trimesh` verification check (testing for watertightness, 0 open edges, and positive signed volume).
* **Self-Repair Loop**: If a validation check fails, the agent intercepts the failure, analyzes the error, dynamically increases the 3D model base thickness parameter to prevent edge intersections, rebuilds the mesh, and re-validates. The loop continues for up to 3 attempts, ensuring the exported STL is guaranteed to succeed in a 3D print slicer.

### 3. Trajectory & Telemetry Logging (Observability)
Every step of the geocoding, parcel query, elevation download, mesh construction, self-repair attempts, and validation results is serialized to a standard `vibe_trajectory.jsonl` log. This provides a complete, audit-ready tracing log of the agent's actions and decisions.

---

## Solving Complex GIS Winding Order & Multi-Part Constraints

ArcGIS servers often present geometric quirks that break standard geometry libraries (like Shapely):
1. **Planar CRS Handoff (`outSR: 6434`)**: Offloads geodetic-to-planar coordinate projection to the ArcGIS backend, returning boundary coordinates directly in Connecticut State Plane Feet. This completely avoids local pyproj transformations and runtime overhead.
2. **Esri JSON Winding Order Correction**: Esri JSON winding orders are the reverse of standard GeoJSON (CW exteriors, CCW interiors). If uncorrected, Shapely misinterprets exterior walls and holes. We implemented a parser using the Shoelace formula (signed area) to identify exterior vs interior rings and map them to Shapely's `Polygon(shell, holes)` constructor, maintaining pristine CCW winding order for the mesh faces.
3. **Multi-Part & Island Geometry**: Disjoint properties (islands or utility easements) are handled using `matplotlib.path.Path` codes (`MOVETO` / `LINETO` / `CLOSEPOLY`), allowing clean boundary jumps without creating ghost triangles or artifacts.

---

## Submission Details
- **GitHub Repository**: [https://github.com/drewjobson/TopoPlot](https://github.com/drewjobson/TopoPlot)
- **Principal Use Case**: Automated exact-parcel 3D terrain twin generation for architectural CAD referencing and 3D printing.
