# data/aqi_utils.py
# ─────────────────────────────────────────────────────────
# AQI helpers aligned with WAQI / US EPA scale (0–500).
# Live AQI comes from WAQI API; forecast uses the same category bands.
# ─────────────────────────────────────────────────────────

from typing import Optional, Tuple

OPENWEATHER_AQI_LABELS = {
    1: "Good",
    2: "Fair",
    3: "Moderate",
    4: "Poor",
    5: "Very Poor",
}

# US EPA PM2.5 breakpoints (µg/m³) — used only when deriving AQI from PM2.5 alone
_US_PM25_BPS = [
    (0.0,   12.0,   0,   50),
    (12.1,  35.4,   51,  100),
    (35.5,  55.4,   101, 150),
    (55.5,  150.4,  151, 200),
    (150.5, 250.4,  201, 300),
    (250.5, 500.4,  301, 500),
]


def waqi_aqi_category(aqi: int) -> str:
    """US EPA / WAQI category labels."""
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Moderate"
    if aqi <= 150:
        return "Unhealthy for Sensitive Groups"
    if aqi <= 200:
        return "Unhealthy"
    if aqi <= 300:
        return "Very Unhealthy"
    return "Hazardous"


def aqi_category(aqi: int) -> str:
    """Alias used by agents — WAQI/US EPA categories."""
    return waqi_aqi_category(aqi)


def us_aqi_from_pm25(pm25: float) -> int:
    """Estimate US EPA AQI from PM2.5 when WAQI index is not available."""
    pm25 = max(0.0, float(pm25))
    for lo_c, hi_c, lo_i, hi_i in _US_PM25_BPS:
        if lo_c <= pm25 <= hi_c:
            return int(round((hi_i - lo_i) / (hi_c - lo_c) * (pm25 - lo_c) + lo_i))
    return 500


def compute_aqi(pm25: float, pm10: float) -> Tuple[int, str]:
    """
    Training / feature-engineering helper: US EPA AQI from PM2.5 and PM10.
    Uses max of PM2.5-based index and a PM10-scaled proxy when PM10 is present.
    """
    aqi25 = us_aqi_from_pm25(pm25)
    aqi10 = us_aqi_from_pm25(pm10 / 1.8) if pm10 else aqi25
    aqi = int(max(aqi25, aqi10))
    return aqi, waqi_aqi_category(aqi)


def scale_aqi_from_pm25(current_aqi: int, current_pm25: float, predicted_pm25: float) -> int:
    """Scale live WAQI AQI proportionally with forecast PM2.5."""
    if current_pm25 <= 0:
        return us_aqi_from_pm25(predicted_pm25)
    ratio = predicted_pm25 / current_pm25
    return int(max(0, min(500, round(current_aqi * ratio))))


def format_openweather_aqi(ow_aqi: int) -> dict:
    """OpenWeather 1–5 scale (fallback pollution source only)."""
    label = OPENWEATHER_AQI_LABELS.get(int(ow_aqi), "Unknown")
    return {
        "value": int(ow_aqi),
        "scale": "openweather_1_5",
        "label": label,
        "display": f"OpenWeather AQI {ow_aqi} ({label})",
    }


def format_waqi_aqi(aqi: int) -> dict:
    cat = waqi_aqi_category(aqi)
    return {
        "value":   int(aqi),
        "scale":   "waqi_us_epa",
        "category": cat,
        "label":   f"Live AQI (WAQI) {aqi} ({cat})",
        "display": f"Live AQI (WAQI) {aqi}",
    }


def pollutant_or_default(value: Optional[float], default: float = 0.0) -> float:
    return float(value) if value is not None else default
