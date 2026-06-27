import requests

CT_ELEVATION_URL = "https://cteco.uconn.edu/ctraster/rest/services/elevation/Statewide2023/ImageServer?f=json"

try:
    r = requests.get(CT_ELEVATION_URL, timeout=10)
    data = r.json()
    print("ImageServer metadata:")
    print("Spatial Reference:", data.get("spatialReference"))
    print("Extent:", data.get("extent"))
except Exception as e:
    print("Error:", e)
