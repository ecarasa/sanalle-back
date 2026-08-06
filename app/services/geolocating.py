import httpx
from app.core.config import settings

async def obtener_coordenadas_osm(direccion: str, ciudad: str = "Buenos Aires"):
    url = "https://nominatim.openstreetmap.org/search"
    
    # Para mejorar la precisión, es ideal concatenar la ciudad y el país.
    # Así evitamos que si ponés "Calle San Martín 123" te devuelva un pueblo en España.
    query_completa = f"{direccion}, {ciudad}, Argentina"
    
    params = {
        "q": query_completa,
        "format": "json",
        "limit": 1
    }
    
    # ¡SÚPER IMPORTANTE! Poné un nombre real de tu app y un mail de contacto.
    headers = {
        "User-Agent": "DrogueriaSanalle/1.0 (notero@versionai.io)"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, params=params, headers=headers, timeout=10.0)
            
            if resp.status_code == 200:
                data = resp.json()
                if len(data) > 0:
                    # Nominatim devuelve la lat y lon como strings, hay que castearlos
                    lat = float(data[0]["lat"])
                    lon = float(data[0]["lon"])
                    return lat, lon
                    
        except httpx.RequestError as exc:
            print(f"Error conectando a Nominatim: {exc}")
            
    # Si la dirección no existe o hay error, devolvemos None
    return None, None




TOMTOM_API_KEY = settings.TOMTOM_API_KEY


async def obtener_coordenadas_tomtom(direccion: str, ciudad: str = "") -> tuple[float | None, float | None]:
    from urllib.parse import quote
    query = f"{direccion}, {ciudad}, Argentina" if ciudad else f"{direccion}, Argentina"
    url = f"https://api.tomtom.com/search/2/geocode/{quote(query)}.json"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                url,
                params={"key": TOMTOM_API_KEY, "countrySet": "AR", "limit": 1},
                timeout=10.0,
            )
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    pos = results[0]["position"]
                    return pos["lat"], pos["lon"]
        except httpx.RequestError as exc:
            print(f"Error conectando a TomTom geocoding: {exc}")
    return None, None


async def obtener_ruta_tomtom(coordenadas_ordenadas: list[tuple[float, float]]) -> dict:
    """
    Recibe una lista de tuplas (latitud, longitud) ya ordenadas lógicamente.
    Devuelve la polyline, distancia total, tiempo total y el detalle por tramo.
    """
    # TomTom espera el formato: lat,lon:lat,lon:lat,lon
    coords_str = ":".join(f"{lat},{lon}" for lat, lon in coordenadas_ordenadas)
    
    url = f"https://api.tomtom.com/routing/1/calculateRoute/{coords_str}/json"
    params = {
        "key": TOMTOM_API_KEY,
        "computeTravelTimeFor": "all",  # Clave: Usa datos de tráfico en tiempo real
        "routeRepresentation": "polyline"
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
        
        if "routes" not in data or not data["routes"]:
            raise ValueError("TomTom no devolvió una ruta válida")
            
        route = data["routes"][0]
        summary = route["summary"]
        
        # 1. Extraer la Polyline (Transformar a [lat, lon] para Leaflet)
        coords = []
        for leg in route["legs"]:
            for pt in leg["points"]:
                coords.append([pt["latitude"], pt["longitude"]])
                
        # 2. Extraer información por cada tramo (entre paradas)
        tramos = []
        for leg in route["legs"]:
            tramos.append({
                "distancia_km": leg["summary"]["lengthInMeters"] / 1000.0,
                "tiempo_minutos": leg["summary"]["travelTimeInSeconds"] / 60.0
            })
            
        return {
            "coords": coords,
            "km": summary["lengthInMeters"] / 1000.0,
            "tiempo_minutos": summary["travelTimeInSeconds"] / 60.0,
            "tramos": tramos
        }