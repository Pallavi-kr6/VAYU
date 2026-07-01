import os
from typing import Any, Dict
import httpx

from config.settings import OSM_OVERPASS_URL

class OSMLanduseClient:
    """Standalone OpenStreetMap Overpass client for land-use features."""

    DEFAULT_URL = "https://overpass-api.de/api/interpreter"

    def __init__(self, overpass_url: str = None):
        self.overpass_url = overpass_url or OSM_OVERPASS_URL or self.DEFAULT_URL
        self.available = bool(self.overpass_url)

    def is_available(self) -> bool:
        return self.available and bool(self.overpass_url)

    def fetch_landuse(self, lat: float, lon: float, radius_m: int = 2000) -> Dict[str, Any]:
        if not self.is_available():
            raise RuntimeError("OSM overpass unavailable")

        query = self._build_query(lat, lon, radius_m)
        try:
            response = httpx.post(self.overpass_url, data={"data": query}, timeout=30.0)
            if response.status_code in {400, 406, 429, 500}:
                self.available = False
                raise RuntimeError(f"OSM Overpass request rejected ({response.status_code})")
            response.raise_for_status()
            payload = response.json()
            return self._to_geojson(payload)
        except Exception as exc:
            self.available = False
            raise RuntimeError(f"OSM Overpass fetch failed: {exc}") from exc

    def _build_query(self, lat: float, lon: float, radius_m: int) -> str:
        return f"""
            [out:json][timeout:30];
            (
              node[highway](around:{radius_m},{lat},{lon});
              way[highway](around:{radius_m},{lat},{lon});
              relation[highway](around:{radius_m},{lat},{lon});
              way[landuse=industrial](around:{radius_m},{lat},{lon});
              relation[landuse=industrial](around:{radius_m},{lat},{lon});
              way[landuse=residential](around:{radius_m},{lat},{lon});
              relation[landuse=residential](around:{radius_m},{lat},{lon});
              way[amenity=hospital](around:{radius_m},{lat},{lon});
              relation[amenity=hospital](around:{radius_m},{lat},{lon});
              way[amenity=school](around:{radius_m},{lat},{lon});
              relation[amenity=school](around:{radius_m},{lat},{lon});
            );
            out body geom;
        """.strip()

    def _to_geojson(self, payload: Any) -> Dict[str, Any]:
        elements = payload.get("elements") or []
        features = []
        for elem in elements:
            geom = self._element_to_geometry(elem)
            if geom is None:
                continue
            features.append({
                "type": "Feature",
                "id": f"{elem.get('type')}/{elem.get('id')}",
                "properties": {
                    "type": elem.get("type"),
                    "tags": elem.get("tags", {}),
                },
                "geometry": geom,
            })
        return {"type": "FeatureCollection", "features": features}

    def _element_to_geometry(self, elem: Dict[str, Any]) -> Any:
        elem_type = elem.get("type")
        if elem_type == "node":
            return {
                "type": "Point",
                "coordinates": [elem.get("lon"), elem.get("lat")],
            }
        if elem_type in {"way", "relation"}:
            if "geometry" in elem:
                coords = [[pt["lon"], pt["lat"]] for pt in elem.get("geometry", [])]
                if not coords:
                    return None
                return {"type": "LineString" if elem_type == "way" else "MultiLineString", "coordinates": coords}
        return None
