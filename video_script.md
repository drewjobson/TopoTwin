# TopoTwin: 5-Minute Video Pitch Script

* **Total Target Duration**: ~4 minutes and 30 seconds (Strictly under the 5-minute limit)
* **Split**: 75% Screen Recording & Slides (Generated Content) | 25% Live Camera & 3D Print Showcase (User Presenting)

---

## Part 1: Intro & The Pitch (Slides / Motion Graphics)
* **Duration**: ~45 seconds (0:00 - 0:45)
* **Visual**: Slides showing architectural mockups and a title card reading: **"TopoTwin: Exact-Boundary 3D Terrain Mesh Generator"**.

### Voiceover (Presenter or Text-To-Speech):
> "For architects, land developers, and 3D printing enthusiasts, modeling real-world terrain is a surprisingly friction-filled process. 
> 
> Traditional tools force users to download generic rectangular bounding-box tiles of the earth. These rectangle tiles waste 3D printing filament, include irrelevant adjacent roads or buildings, and fail to isolate the actual plot of land you are designing for.
> 
> Introducing **TopoTwin**.
> 
> TopoTwin is an agentic geospatial mesh engine that automates the entire ingestion and modeling pipeline. By geocoding any target address, querying municipal tax assessor databases, and downloading statewide 2-foot resolution bare-earth LiDAR elevation models, TopoTwin constructs a mathematically watertight 3D solid manifold shaped precisely like the legal property boundary."

---

## Part 2: Interactive Web Application Walkthrough (Screen Recording)
* **Duration**: ~1 minute 30 seconds (0:45 - 2:15)
* **Visual**: Screen capture of the live Streamlit app running at `topotwin.onrender.com`.

### Voiceover:
> "Let’s look at the live application.
> 
> In the sidebar, the user can search any address in Connecticut. The system features real-time autocompletion, querying the ArcGIS geocoding servers on every keystroke. Selecting an address instantly resolves and locks in the centroid coordinates.
> 
> When we click 'Generate 3D Terrain', the application initiates the background pipeline. A live status monitor logs every stage: geocoding, querying the parcel boundaries, pulling elevation samples, and running triangulation checks.
> 
> As you can see, the resulting 3D model is clipped exactly to the property line. Above the visualizer, we can toggle between different rendering styles: Solid, Wireframe, Solid + Wireframe, and Solid + Contours, which dynamically slices the mesh at fixed elevation intervals.
> 
> For sites outside Connecticut or custom projects, users can upload their own GeoJSON, KML, or zipped Shapefile boundaries in the sidebar. This overrides the address search and immediately projects the custom boundary to Web Mercator, queries the USGS elevation database, and builds the mesh.
> 
> Finally, the model can be exported instantly to STL for 3D printing, Wavefront OBJ, 3MF, or a vertex-colored PLY file for direct rendering in Blender."

---

## Part 3: Under the Hood — Architecture, Gating, & Self-Repair (Slides & Code)
* **Duration**: ~1 minute 05 seconds (2:15 - 3:20)
* **Visual**: Slides showing the system flow diagram, followed by quick cuts of the code in VS Code showing `harness/policy_server.py` and `harness/validator.py`.

### Voiceover:
> "Under the hood, TopoTwin demonstrates the key concept from the Kaggle course: **Agent = Model + Harness**.
> 
> First, **Structural & Semantic Gating**: The agent operates behind a policy engine. Viewer roles are structurally blocked from executing dangerous shell tools. Additionally, semantic gating intercepts all coordinates before external API requests are made, immediately blocking and logging queries targeting restricted locations like Area 51.
> 
> Second, the **Validation-Driven Self-Repair Loop**: Organic property boundaries can lead to non-manifold edges. TopoTwin automatically pipes every generated mesh through a Trimesh validator. If open boundaries are detected, the system executes a self-repair loop: correcting face normals, filling holes, and dynamically thickening the base up to 3 times until the validation harness returns a PASS.
> 
> Third, **Observability**: Every single geocode, parcel boundary coordinate, and self-repair iteration is serialized to `vibe_trajectory.jsonl`, providing a complete OpenTelemetry-style log of the agent's actions."

---

## Part 4: Live Camera & Physical 3D Print Showcase (Camera on Presenter)
* **Duration**: ~1 minute 10 seconds (3:20 - 4:30)
* **Visual**: You talking directly to the camera, holding and showcasing a physical 3D printed terrain model exported from TopoTwin.

### Speaker (Drew):
> "And here is the final result. 
> 
> *(Hold up the physical 3D print close to the camera, tilting it so the lens captures the irregular boundary edges and the terrain contours).*
> 
> This is a physical print of the Hartford Public Library terrain model generated directly by TopoTwin. 
> 
> Note how clean the flat solid base is, and how the vertical skirt walls follow the exact municipal boundary lines without any stringing or overhang defects. The bare-earth LiDAR DEM captures the subtle elevation variations of the site, which is invaluable for architects presenting models to clients or planners.
> 
> To achieve a clean print like this, the TopoTwin guide recommends slicing with the **Arachne Wall Generator** in OrcaSlicer to fill the sharp property corners. And on high-speed CoreXY printers like the Creality K1, reducing outer wall acceleration to 1000 mm/s² prevents mechanical ringing along these irregular perimeter skirts.
> 
> With TopoTwin, we have transformed non-deterministic spatial data into physical, watertight reality. 
> 
> The project is open-source, fully tested, and live on Render. Thank you for watching!"
