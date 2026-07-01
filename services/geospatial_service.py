import logging
from typing import Dict, Any

from config.settings import (
    ENABLE_NASA_FIRMS,
    ENABLE_OSM,
    ENABLE_SENTINEL,
)
from geospatial.sentinel_client import SentinelClient
from geospatial.nasa_firms_client import NASAFIRMSClient
from geospatial.osm_landuse_client import OSMLanduseClient
from geospatial.heatmap_utils import risk_scores_to_buckets

logger = logging.getLogger(__name__)

class GeoSpatialService:
    """Combine optional geospatial sources into pollution risk insights."""

    def __init__(self):
        self.sentinel = SentinelClient() if ENABLE_SENTINEL else None
        self.nasa = NASAFIRMSClient() if ENABLE_NASA_FIRMS else None
        self.osm = OSMLanduseClient() if ENABLE_OSM else None

    def get_insights(self, lat: float, lon: float) -> Dict[str, Any]:
        vegetation_index = 0.0
        fire_hotspots = []
        fire_hotspot_summary = {
            "status": "success",
            "count": 0,
            "hotspots": [],
            "message": "No active fire hotspots detected in this area during the selected period.",
        }
        land_use_geojson = {"type": "FeatureCollection", "features": []}
        pollution_risk_factors = {
            "vehicular": 0.0,
            "industrial": 0.0,
            "biomass": 0.0,
        }
        provider_successes = {
            "sentinel": False,
            "nasa": False,
            "osm": False,
        }

        if self.sentinel is not None and getattr(self.sentinel, "is_available", lambda: True)():
            try:
                ndvi_payload = self.sentinel.fetch_ndvi(lat, lon)
                vegetation_index = float(ndvi_payload.get("ndvi", 0.0))
                provider_successes["sentinel"] = True
            except Exception as exc:
                logger.info("Sentinel NDVI unavailable: %s", exc)

        if self.nasa is not None and getattr(self.nasa, "is_available", lambda: True)():
            try:
                fire_hotspots = self.nasa.fetch_hotspots(lat, lon)
                biomass_score = self._compute_biomass_score(fire_hotspots)
                pollution_risk_factors["biomass"] = biomass_score
                fire_hotspot_summary = {
                    "status": "success",
                    "count": len(fire_hotspots),
                    "hotspots": fire_hotspots,
                    "message": (
                        "No active fire hotspots detected in this area during the selected period."
                        if not fire_hotspots
                        else f"Detected {len(fire_hotspots)} active fire hotspot(s) in the selected area."
                    ),
                }
                provider_successes["nasa"] = True
            except Exception as exc:
                logger.info("NASA FIRMS unavailable: %s", exc)

        if self.osm is not None and getattr(self.osm, "is_available", lambda: True)():
            try:
                land_use_geojson = self.osm.fetch_landuse(lat, lon)
                vehicular_score, industrial_score = self._compute_infrastructure_scores(land_use_geojson)
                pollution_risk_factors["vehicular"] = vehicular_score
                pollution_risk_factors["industrial"] = industrial_score
                provider_successes["osm"] = True
            except Exception as exc:
                logger.info("OSM land-use unavailable: %s", exc)

        confidence_score = self._compute_confidence(provider_successes)
        risk_buckets = risk_scores_to_buckets(pollution_risk_factors)

        return {
            "location": {"lat": lat, "lon": lon},
            "insights": {
                "vegetation_index": vegetation_index,
                "fire_hotspots": fire_hotspots,
                "fire_hotspot_summary": fire_hotspot_summary,
                "land_use": land_use_geojson,
                "pollution_risk_factors": pollution_risk_factors,
                "risk_buckets": risk_buckets,
            },
            "confidence_score": confidence_score,
        }

    def _compute_biomass_score(self, hotspots: list) -> float:
        if not hotspots:
            return 0.0
        brightness = sum(h.get("brightness", 0.0) for h in hotspots)
        count = len(hotspots)
        score = min((brightness / max(count, 1)) / 400.0, 1.0)
        return round(score, 3)

    def _compute_infrastructure_scores(self, land_use_geojson: dict) -> tuple:
        vehicular = 0.0
        industrial = 0.0
        tags = [feat.get("properties", {}).get("tags", {}) for feat in land_use_geojson.get("features", [])]

        highway_count = sum(1 for t in tags if "highway" in t)
        industrial_area = sum(1 for t in tags if t.get("landuse") == "industrial")
        vehicular = min(highway_count / 15.0, 1.0)
        industrial = min(industrial_area / 8.0, 1.0)

        return round(vehicular, 3), round(industrial, 3)

    def _compute_confidence(self, provider_successes: dict) -> float:
        active_sources = 0
        if self.sentinel is not None:
            active_sources += 1
        if self.nasa is not None:
            active_sources += 1
        if self.osm is not None:
            active_sources += 1

        if active_sources == 0:
            return 0.0

        successful_sources = sum(1 for source in provider_successes.values() if source)
        if successful_sources == 0:
            return 0.0

        coverage = 0.0
        if self.sentinel is not None:
            coverage += 0.25 if provider_successes.get("sentinel", False) else 0.0
        if self.nasa is not None:
            coverage += 0.4 if provider_successes.get("nasa", False) else 0.0
        if self.osm is not None:
            coverage += 0.35 if provider_successes.get("osm", False) else 0.0

        return round(min(coverage, 1.0), 3)
