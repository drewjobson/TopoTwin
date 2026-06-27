import numpy as np
from shapely.geometry import shape, Polygon as ShapelyPolygon, MultiPolygon as ShapelyMultiPolygon


def build_polygon_outline_model_coords(
    geometry_geojson: dict,
    points_2d: np.ndarray,
    elevations_m: np.ndarray,
    model_scale: float,
    z_exaggeration: float
) -> list[tuple[float, float, float]]:
    """Builds the 3D property boundary outline in model-space (mm) coordinates.

    Iterates all exterior and interior rings of the parcel geometry, projects each
    vertex to scaled model coordinates, and finds the nearest DEM elevation for the
    Z component. Rings are separated by (None, None, None) sentinels for Plotly.

    Args:
        geometry_geojson: GeoJSON dict of the parcel boundary (Polygon or MultiPolygon).
        points_2d: (N, 2) array of DEM sample point coordinates (feet, EPSG:6434).
        elevations_m: (N,) array of elevations in meters, matching points_2d.
        model_scale: Scale factor from real-world meters to model mm.
        z_exaggeration: Vertical exaggeration multiplier.

    Returns:
        List of (x_mm, y_mm, z_mm) tuples with None sentinels between rings.
    """
    poly_shape = shape(geometry_geojson)

    X_scaled_all = (points_2d[:, 0] * 0.3048) * model_scale
    Y_scaled_all = (points_2d[:, 1] * 0.3048) * model_scale
    min_x_scaled = np.min(X_scaled_all)
    min_y_scaled = np.min(Y_scaled_all)

    # Gather all rings (exteriors and interiors of all parts)
    rings: list[list] = []
    if isinstance(poly_shape, ShapelyPolygon):
        rings.append(list(poly_shape.exterior.coords))
        for hole in poly_shape.interiors:
            rings.append(list(hole.coords))
    elif isinstance(poly_shape, ShapelyMultiPolygon):
        for sub_poly in poly_shape.geoms:
            rings.append(list(sub_poly.exterior.coords))
            for hole in sub_poly.interiors:
                rings.append(list(hole.coords))

    polygon_coords_model: list[tuple[float, float, float]] = []
    first_ring = True
    for ring in rings:
        if not first_ring:
            polygon_coords_model.append((None, None, None))
        first_ring = False

        for pt in ring:
            x_ft, y_ft = pt[0], pt[1]
            x_mm = x_ft * 0.3048 * model_scale
            y_mm = y_ft * 0.3048 * model_scale

            # Nearest-neighbor Z lookup
            dists = np.hypot(points_2d[:, 0] - x_ft, points_2d[:, 1] - y_ft)
            nearest_idx = np.argmin(dists)
            z_mm = elevations_m[nearest_idx] * z_exaggeration * model_scale

            # Apply origin shift
            x_mm -= min_x_scaled
            y_mm -= min_y_scaled

            polygon_coords_model.append((x_mm, y_mm, z_mm + 0.5))

    return polygon_coords_model


def parse_kml_geometry(kml_content: bytes | str) -> dict | None:
    """Parses a KML file and extracts the first Polygon geometry as GeoJSON.

    Uses Python's built-in xml.etree.ElementTree — no external dependencies.

    Args:
        kml_content: Raw KML file content (bytes or string).

    Returns:
        GeoJSON-style geometry dict, or None if no polygon found.
    """
    import xml.etree.ElementTree as ET

    if isinstance(kml_content, bytes):
        kml_content = kml_content.decode("utf-8")

    # Strip BOM if present
    kml_content = kml_content.lstrip("\ufeff")

    root = ET.fromstring(kml_content)

    # KML namespace
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    def _find_all(tag: str):
        return root.iter(f"{ns}{tag}")

    def _parse_coord_string(coord_str: str) -> list[list[float]]:
        """Parses 'lon,lat,alt lon,lat,alt ...' into [[lon, lat], ...]."""
        coords = []
        for token in coord_str.strip().split():
            parts = token.split(",")
            if len(parts) >= 2:
                coords.append([float(parts[0]), float(parts[1])])
        return coords

    # Find the first Polygon element
    for polygon_elem in _find_all("Polygon"):
        outer_ring = polygon_elem.find(f".//{ns}outerBoundaryIs/{ns}LinearRing/{ns}coordinates")
        if outer_ring is None or not outer_ring.text:
            continue

        exterior_coords = _parse_coord_string(outer_ring.text)
        if len(exterior_coords) < 3:
            continue

        # Close ring if needed
        if exterior_coords[0] != exterior_coords[-1]:
            exterior_coords.append(exterior_coords[0])

        # Parse inner rings (holes)
        holes = []
        for inner_elem in polygon_elem.findall(f".//{ns}innerBoundaryIs/{ns}LinearRing/{ns}coordinates"):
            if inner_elem.text:
                hole_coords = _parse_coord_string(inner_elem.text)
                if len(hole_coords) >= 3:
                    if hole_coords[0] != hole_coords[-1]:
                        hole_coords.append(hole_coords[0])
                    holes.append(hole_coords)

        geojson = {
            "type": "Polygon",
            "coordinates": [exterior_coords] + holes
        }
        return geojson

    return None


def parse_shapefile_zip(zip_bytes: bytes) -> dict | None:
    """Parses a zipped Shapefile (.zip containing .shp, .shx, .dbf) and extracts
    the first Polygon/MultiPolygon geometry as GeoJSON.

    Uses the pure-Python `shapefile` (pyshp) library — no GDAL/C dependencies.

    Args:
        zip_bytes: Raw ZIP file content.

    Returns:
        GeoJSON-style geometry dict, or None if no polygon found.
    """
    import zipfile
    import io
    import tempfile
    import os

    try:
        import shapefile
    except ImportError:
        raise ImportError(
            "The 'pyshp' package is required to read Shapefiles. "
            "Install it with: pip install pyshp"
        )

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        # Extract to a temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            zf.extractall(tmpdir)

            # Find the .shp file
            shp_files = []
            for root_dir, _dirs, files in os.walk(tmpdir):
                for f in files:
                    if f.lower().endswith(".shp"):
                        shp_files.append(os.path.join(root_dir, f))

            if not shp_files:
                return None

            reader = shapefile.Reader(shp_files[0])
            for sr in reader.shapeRecords():
                geojson = sr.shape.__geo_interface__
                if geojson.get("type") in ("Polygon", "MultiPolygon"):
                    return geojson

    return None
