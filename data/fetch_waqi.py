# data/fetch_waqi.py
# ─────────────────────────────────────────────────────────
# WAQI (World Air Quality Index) — live pollutant + AQI readings.
#
# Why WAQI for pollutants:
#   OpenWeather Air Pollution returns a coarse 1–5 index and often
#   underestimates PM2.5 for Indian cities. WAQI aggregates real monitoring
#   stations (US EPA / local EPA scale 0–500) and is better aligned with
#   on-the-ground AQI in Delhi, Mumbai, etc.
#
# OpenWeather is still used separately for meteorology (temp, humidity, wind,
# pressure, rain) — see data/download_data.py fetch_openweather_live().
# ─────────────────────────────────────────────────────────

import time
from typing import Any, Optional

import requests
from loguru import logger

WAQI_BASE = "https://api.waqi.info"

# WAQI feed slug aliases (geo feed is preferred; names are fallback)
WAQI_CITY_ALIASES = {
    "delhi":     "delhi",
    "mumbai":    "mumbai",
    "bengaluru": "bangalore",
    "kolkata":   "kolkata",
    "chennai":   "chennai",
    "hyderabad": "hyderabad",
}


def _iaqi_value(iaqi: dict, key: str) -> Optional[float]:
    """Extract pollutant from WAQI iaqi block; None if missing."""
    if not iaqi or key not in iaqi:
        return None
    entry = iaqi[key]
    if isinstance(entry, dict) and "v" in entry:
        try:
            return float(entry["v"])
        except (TypeError, ValueError):
            return None
    return None


def _request_waqi(url: str, max_retries: int = 3) -> dict:
    """GET with exponential backoff."""
    last_err = None
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=12)
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("status") != "ok":
                raise RuntimeError(payload.get("data", payload.get("status", "unknown error")))
            return payload
        except Exception as e:
            last_err = e
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(f"WAQI request failed (attempt {attempt + 1}): {e} — retry in {wait}s")
                time.sleep(wait)
    raise RuntimeError(f"WAQI API failed after {max_retries} attempts: {last_err}")


def _parse_waqi_payload(payload: dict, city: str) -> dict:
    data = payload.get("data") or {}
    iaqi = data.get("iaqi") or {}

    aqi_raw = data.get("aqi")
    if aqi_raw == "-" or aqi_raw is None:
        raise RuntimeError("WAQI returned no AQI value for this location")

    return {
        "city":   city.lower(),
        "aqi":    int(float(aqi_raw)),
        "pm25":   _iaqi_value(iaqi, "pm25"),
        "pm10":   _iaqi_value(iaqi, "pm10"),
        "o3":     _iaqi_value(iaqi, "o3"),
        "no2":    _iaqi_value(iaqi, "no2"),
        "so2":    _iaqi_value(iaqi, "so2"),
        "co":     _iaqi_value(iaqi, "co"),
        "source": "WAQI",
        "station": (data.get("city") or {}).get("name"),
        "time":   (data.get("time") or {}).get("s"),
    }


def fetch_waqi_live(city: str, api_key: str = None, lat: float = None, lon: float = None) -> dict:
    """
    Fetch live AQI + pollutants from WAQI for a city.

    Tries geo feed (lat/lon) first, then city-name feed.
    Missing pollutants are returned as None (never raises for absent iaqi keys).

    Returns:
        {
            "city": "delhi", "aqi": 132, "pm25": 68.4, "pm10": 102.1,
            "o3": 12.0, "no2": 29.0, "so2": 4.0, "co": 0.8, "source": "WAQI"
        }
    """
    from config.settings import WAQI_API_KEY, CITIES

    token = api_key or WAQI_API_KEY
    if not token:
        raise RuntimeError("WAQI_API_KEY is required. Set it in .env")

    city_key = city.lower().strip()
    coords = CITIES.get(city_key, {})
    lat = lat if lat is not None else coords.get("lat")
    lon = lon if lon is not None else coords.get("lon")

    errors = []

    if lat is not None and lon is not None:
        geo_url = f"{WAQI_BASE}/feed/geo:{lat};{lon}/?token={token}"
        try:
            result = _parse_waqi_payload(_request_waqi(geo_url), city_key)
            logger.success(
                f"WAQI [{city_key}] AQI={result['aqi']} "
                f"PM2.5={result['pm25']} PM10={result['pm10']}"
            )
            return result
        except Exception as e:
            errors.append(f"geo:{e}")

    slug = WAQI_CITY_ALIASES.get(city_key, city_key)
    city_url = f"{WAQI_BASE}/feed/{slug}/?token={token}"
    try:
        result = _parse_waqi_payload(_request_waqi(city_url), city_key)
        logger.success(
            f"WAQI [{city_key}] AQI={result['aqi']} "
            f"PM2.5={result['pm25']} PM10={result['pm10']}"
        )
        return result
    except Exception as e:
        errors.append(f"city:{e}")

    raise RuntimeError(f"WAQI unavailable for {city_key}: {'; '.join(errors)}")
