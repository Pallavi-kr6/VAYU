import unittest

from services.geospatial_service import GeoSpatialService


class GeoSpatialServiceFallbackTests(unittest.TestCase):
    def test_returns_empty_fallback_when_all_providers_fail(self):
        service = GeoSpatialService()
        service.sentinel = type("BrokenSentinel", (), {"fetch_ndvi": lambda self, lat, lon: (_ for _ in ()).throw(RuntimeError("boom"))})()
        service.nasa = type("BrokenNASA", (), {"fetch_hotspots": lambda self, lat, lon: (_ for _ in ()).throw(RuntimeError("boom"))})()
        service.osm = type("BrokenOSM", (), {"fetch_landuse": lambda self, lat, lon: (_ for _ in ()).throw(RuntimeError("boom"))})()

        result = service.get_insights(22.5726, 88.3639)

        self.assertEqual(result["location"], {"lat": 22.5726, "lon": 88.3639})
        self.assertEqual(result["insights"]["fire_hotspots"], [])
        self.assertEqual(result["insights"]["fire_hotspot_summary"], {
            "status": "success",
            "count": 0,
            "hotspots": [],
            "message": "No active fire hotspots detected in this area during the selected period.",
        })
        self.assertEqual(result["insights"]["land_use"], {"type": "FeatureCollection", "features": []})
        self.assertEqual(result["insights"]["pollution_risk_factors"], {"vehicular": 0.0, "industrial": 0.0, "biomass": 0.0})
        self.assertEqual(result["confidence_score"], 0.0)


if __name__ == "__main__":
    unittest.main()
