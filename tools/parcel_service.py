import requests

from tools.context_resolver import resolve_context

# Connecticut statewide parcel layer FeatureServer query URL
CT_PARCEL_URL = resolve_context("[[CT_PARCEL_URL]]")

def is_point_in_polygon(lon: float, lat: float, polygon: list[list[float]]) -> bool:
    """Checks if a point (lon, lat) is inside a polygon using the Ray Casting algorithm."""
    num = len(polygon)
    j = num - 1
    c = False
    for i in range(num):
        px, py = polygon[i][0], polygon[i][1]
        jx, jy = polygon[j][0], polygon[j][1]
        
        # Ray casting check
        if ((py > lat) != (jy > lat)) and \
           (lon < (jx - px) * (lat - py) / (jy - py + 1e-12) + px):
            c = not c
        j = i
    return c

def signed_area(ring: list[list[float]]) -> float:
    """Calculates the signed area of a 2D ring using the Shoelace formula.
    Positive area = Counter-Clockwise (CCW).
    Negative area = Clockwise (CW).
    """
    area = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        area += x1 * y2 - x2 * y1
    return 0.5 * area

def esri_geometry_to_shapely(esri_geom: dict):
    """Parses Esri JSON geometry (with 'rings') to a Shapely Polygon or MultiPolygon,
    ensuring correct shell/hole containment using the Shoelace formula and Shapely.
    """
    from shapely.geometry import Polygon as ShapelyPolygon, MultiPolygon as ShapelyMultiPolygon
    
    rings = esri_geom.get("rings", [])
    exteriors = []
    interiors = []
    
    for ring in rings:
        if len(ring) < 3:
            continue
        closed_ring = list(ring)
        if closed_ring[0] != closed_ring[-1]:
            closed_ring.append(closed_ring[0])
            
        area = signed_area(closed_ring)
        if area < 0:  # Clockwise = Esri Exterior
            exteriors.append(closed_ring)
        else:  # Counter-Clockwise = Esri Interior (hole)
            interiors.append(closed_ring)
            
    if not exteriors:
        if not interiors:
            raise ValueError("No valid rings found in Esri geometry.")
        # Fallback: assume the ring with the largest absolute area is exterior
        interiors_sorted = sorted(interiors, key=lambda r: abs(signed_area(r)), reverse=True)
        exteriors = [interiors_sorted[0]]
        interiors = interiors_sorted[1:]
        
    exterior_polys = [ShapelyPolygon(ext) for ext in exteriors]
    poly_groups = {i: [] for i in range(len(exteriors))}
    
    for hole in interiors:
        hole_poly = ShapelyPolygon(hole)
        found = False
        for idx, ext_poly in enumerate(exterior_polys):
            if ext_poly.contains(hole_poly):
                poly_groups[idx].append(hole)
                found = True
                break
        if not found:
            poly_groups[0].append(hole)
            
    polygons = []
    for idx, ext in enumerate(exteriors):
        holes = poly_groups[idx]
        polygons.append(ShapelyPolygon(shell=ext, holes=holes))
        
    if len(polygons) == 1:
        return polygons[0]
    else:
        return ShapelyMultiPolygon(polygons)

def query_ct_parcel(lat: float, lon: float, force_format: str = None) -> dict | None:
    """Queries the Connecticut CAMA and Parcel Layer Feature Server.
    
    Finds the property parcel containing the given coordinates.
    
    Args:
        lat (float): Latitude.
        lon (float): Longitude.
        force_format (str): If 'geojson' or 'json', forces that query format.
        
    Returns:
        dict: A dictionary containing:
              - 'geometry': dict, the GeoJSON geometry (Polygon or MultiPolygon) in EPSG:6434.
              - 'address': str, resolved property address.
              - 'owner': str, property owner.
              - 'town': str, town name.
              - 'parcel_id': str, municipal parcel ID.
        Or None if no parcel is found or coordinates are outside CT.
    """
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": "15",
        "units": "esriSRUnit_Meter",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "2234"
    }
    
    try_geojson = force_format != "json"
    data = None
    geojson_supported = False
    
    if try_geojson:
        g_params = params.copy()
        g_params["f"] = "geojson"
        try:
            response = requests.get(CT_PARCEL_URL, params=g_params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "error" not in data and "features" in data:
                    if len(data["features"]) > 0:
                        first_geom = data["features"][0].get("geometry", {})
                        if "rings" not in first_geom:
                            geojson_supported = True
                        else:
                            print("  ArcGIS Online FeatureServer returned Esri JSON despite f=geojson.")
                    else:
                        geojson_supported = True
                else:
                    print(f"  ArcGIS Online FeatureServer geojson query returned error or invalid format.")
            else:
                print(f"  ArcGIS Online FeatureServer geojson query failed with status code {response.status_code}")
        except Exception as e:
            print(f"  ArcGIS Online FeatureServer geojson query raised exception: {e}")
            
    if not geojson_supported:
        print("  Querying parcel boundaries via f=json (Esri JSON)...")
        j_params = params.copy()
        j_params["f"] = "json"
        try:
            response = requests.get(CT_PARCEL_URL, params=j_params, timeout=10)
            if response.status_code == 200:
                data = response.json()
            else:
                print(f"  ArcGIS Online FeatureServer json query failed with status code {response.status_code}")
                return None
        except Exception as e:
            print(f"  ArcGIS Online FeatureServer json query raised exception: {e}")
            return None
            
    if not data:
        return None
        
    features = data.get("features", [])
    if not features:
        return None
        
    # Project the query point to EPSG:6434 for distance calculations
    from pyproj import Transformer
    from shapely.geometry import Point
    transformer_to_6434 = Transformer.from_crs("EPSG:4326", "EPSG:6434", always_xy=True)
    x_query, y_query = transformer_to_6434.transform(lon, lat)
    p_query = Point(x_query, y_query)

    # Project candidate geometries from EPSG:2234 to EPSG:6434
    transformer_2234_to_6434 = Transformer.from_crs("EPSG:2234", "EPSG:6434", always_xy=True)
    from shapely.ops import transform
    from shapely.geometry import shape, mapping

    candidates = []
    for f in features:
        props = f.get("properties") or f.get("attributes") or {}
        
        # Standardize field lookups
        owner = props.get("Owner1") or props.get("OWNER") or props.get("Owner") or ""
        addr = props.get("Location_1") or props.get("Location") or props.get("SiteAddress") or props.get("LOC_ADR") or ""
        parcel_id = props.get("Mbl") or props.get("PARCEL_ID") or props.get("Map_Block_Lot") or ""
        parcel_typ = str(props.get("Parcel_Typ") or "").upper()
        
        owner_str = str(owner).upper()
        addr_str = str(addr).upper()
        parcel_id_str = str(parcel_id).upper()
        
        # Detect Right-Of-Way (road network)
        is_row = (
            parcel_typ == "ROW" or
            parcel_id_str == "ROW" or
            "RIGHT OF WAY" in owner_str or
            "RIGHT-OF-WAY" in owner_str or
            "TOWN ROAD" in owner_str or
            "STATE OF CONNECTICUT (ROW)" in owner_str or
            (owner_str == "UNKNOWN" and addr_str == "UNKNOWN" and parcel_id_str == "UNKNOWN") or
            (not owner and not addr and not parcel_id)
        )
        
        if is_row:
            print(f"  Skipping municipal Right-of-Way feature in search buffer for '{addr or 'Unknown Road'}'...")
            continue
            
        geom = f.get("geometry", {})
        try:
            if "rings" in geom:
                shapely_geom = esri_geometry_to_shapely(geom)
            else:
                shapely_geom = shape(geom)
                
            shapely_geom_6434 = transform(transformer_2234_to_6434.transform, shapely_geom)
            dist_ft = p_query.distance(shapely_geom_6434)
            candidates.append((dist_ft, f, shapely_geom_6434))
        except Exception as e:
            print(f"  Error parsing or transforming geometry for '{addr}': {e}")
            continue

    if candidates:
        # Sort by distance (closest first)
        candidates.sort(key=lambda x: x[0])
        dist_ft, feature, shapely_geom_6434 = candidates[0]
        addr_selected = (
            feature.get("properties", {}).get("Location_1") or 
            feature.get("attributes", {}).get("Location_1") or 
            "Unknown Address"
        )
        print(f"  Selected closest residential parcel: '{addr_selected}' (Distance: {dist_ft:.2f} feet)")
    else:
        print("  No residential property parcel found in buffer. Falling back to first returned feature.")
        feature = features[0]
        geom = feature.get("geometry", {})
        try:
            if "rings" in geom:
                shapely_geom = esri_geometry_to_shapely(geom)
            else:
                shapely_geom = shape(geom)
            shapely_geom_6434 = transform(transformer_2234_to_6434.transform, shapely_geom)
        except Exception as e:
            print(f"  Error parsing fallback geometry: {e}")
            return None

    props = feature.get("properties") or feature.get("attributes") or {}
    owner = props.get("Owner1") or props.get("OWNER") or props.get("Owner") or "Unknown Owner"
    addr = props.get("Location_1") or props.get("Location") or props.get("SiteAddress") or props.get("LOC_ADR") or "Unknown Address"
    town = props.get("Town_Name") or props.get("TOWN") or "Unknown Town"
    parcel_id = props.get("Mbl") or props.get("PARCEL_ID") or props.get("Map_Block_Lot") or "Unknown ID"
    
    geom = mapping(shapely_geom_6434)
            
    return {
        "geometry": geom,
        "address": addr,
        "owner": owner,
        "town": town,
        "parcel_id": parcel_id
    }

if __name__ == "__main__":
    # Test with coordinates in Clinton, CT
    res = query_ct_parcel(41.27871, -72.52759)
    if res:
        print("Successfully found parcel!")
        print(f"Address: {res['address']}")
        print(f"Owner: {res['owner']}")
        print(f"Town: {res['town']}")
        print(f"Geometry Type: {res['geometry'].get('type')}")
    else:
        print("Parcel not found or service down.")
