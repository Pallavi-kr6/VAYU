# data/aqi_utils.py
# ─────────────────────────────────────────────────────────
# Single authoritative AQI path for VAYU (CPCB India standard).
# OpenWeather uses a separate 1–5 scale — never mix with CPCB AQI.
# ─────────────────────────────────────────────────────────

from typing import Tuple

# CPCB sub-index breakpoints (µg/m³ for PM, ppb/µg for gases)
_PM25_BPS = [
    (0, 30, 0, 50, "Good"),
    (30, 60, 51, 100, "Satisfactory"),
    (60, 90, 101, 200, "Moderate"),
    (90, 120, 201, 300, "Poor"),
    (120, 250, 301, 400, "Very Poor"),
    (250, 500, 401, 500, "Severe"),
]
_PM10_BPS = [
    (0, 50, 0, 50, "Good"),
    (50, 100, 51, 100, "Satisfactory"),
    (100, 250, 101, 200, "Moderate"),
    (250, 350, 201, 300, "Poor"),
    (350, 430, 301, 400, "Very Poor"),
    (430, 600, 401, 500, "Severe"),
]

OPENWEATHER_AQI_LABELS = {
    1: "Good",
    2: "Fair",
    3: "Moderate",
    4: "Poor",
    5: "Very Poor",
}


def sub_index(value: float, breakpoints: list) -> Tuple[int, str]:
    for lo_c, hi_c, lo_i, hi_i, cat in breakpoints:
        if lo_c <= value <= hi_c:
            aqi = (hi_i - lo_i) / (hi_c - lo_c) * (value - lo_c) + lo_i
            return round(aqi), cat
    return 500, "Severe"


def compute_cpcb_aqi(pm25: float, pm10: float) -> Tuple[int, str]:
    """CPCB National Air Quality Index (PM2.5 + PM10 sub-indices, max wins)."""
    pm25 = max(0.0, float(pm25))
    pm10 = max(0.0, float(pm10))
    aqi25, cat25 = sub_index(pm25, _PM25_BPS)
    aqi10, cat10 = sub_index(pm10, _PM10_BPS)
    aqi = max(aqi25, aqi10)
    cat = cat25 if aqi25 >= aqi10 else cat10
    return int(aqi), cat


def aqi_category(aqi: int) -> str:
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Satisfactory"
    if aqi <= 200:
        return "Moderate"
    if aqi <= 300:
        return "Poor"
    if aqi <= 400:
        return "Very Poor"
    return "Severe"


def format_openweather_aqi(ow_aqi: int) -> dict:
    """OpenWeather 1–5 scale metadata (not CPCB)."""
    label = OPENWEATHER_AQI_LABELS.get(int(ow_aqi), "Unknown")
    return {
        "value": int(ow_aqi),
        "scale": "openweather_1_5",
        "label": label,
        "display": f"OpenWeather AQI {ow_aqi} ({label})",
    }
