# data/download_data.py
# ─────────────────────────────────────────────────────────
# Downloads all training data:
#   1. Kaggle: Historical OpenWeather / India AQI (2015-2024)
#   2. Kaggle: India AQI Real-Time 2023-2025
#   3. Sentinel-5P NO2/SO2 via Google Earth Engine
#   4. OpenWeather historical (fallback if IMD unavailable)
# ─────────────────────────────────────────────────────────

import os, json, zipfile, subprocess
from pathlib import Path
import pandas as pd
import requests
from loguru import logger

sys_path = Path(__file__).parent.parent
RAW_DIR = sys_path / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────────
# 1. KAGGLE DATASETS
# ─────────────────────────────────────────────────────────
KAGGLE_DATASETS = [
    # Historical AQI 2015–2024 (gold standard training data)
    {
        "slug":  "rohanrao/air-quality-data-in-india",
        "name":  "aqi_india_2015_2024",
    },
    # Real-time AQI 2023–2025 (recent validation data)
    {
        "slug":  "abhisheksjha/time-series-air-quality-data-of-india-2010-2023",
        "name":  "aqi_timeseries_2010_2023",
    },
    # Indian Climate with AQI 2024-2025
    {
        "slug":  "ankushnarwade/indian-climate-dataset-20242025",
        "name":  "indian_climate_2024_2025",
    },
    # Comprehensive cybercrime / fraud (not needed here — AQI only)
]

def download_kaggle_datasets():
    """Download datasets via Kaggle CLI. Requires ~/.kaggle/kaggle.json"""
    logger.info("Downloading Kaggle datasets...")

    for ds in KAGGLE_DATASETS:
        out_dir = RAW_DIR / ds["name"]
        if out_dir.exists() and any(out_dir.iterdir()):
            logger.info(f"  ✓ {ds['name']} already downloaded")
            continue

        out_dir.mkdir(exist_ok=True)
        cmd = [
            "kaggle", "datasets", "download",
            "-d", ds["slug"],
            "-p", str(out_dir),
            "--unzip"
        ]
        logger.info(f"  Downloading {ds['slug']}...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning(f"  Failed: {result.stderr}. Creating synthetic data instead.")
            create_synthetic_aqi_data(out_dir, ds["name"])
        else:
            logger.success(f"  ✓ {ds['name']}")


# ─────────────────────────────────────────────────────────
# 2. OPENWEATHER LIVE API  (15-minute AQI readings)
# ─────────────────────────────────────────────────────────
OPENWEATHER_API_BASE = "https://api.openweathermap.org/data/2.5"

def fetch_openweather_live(city: str, api_key: str = None) -> pd.DataFrame:
    """
    Fetch live air quality + weather from OpenWeather.

    Calls two OpenWeather endpoints:
      1. Air Pollution API  → PM2.5, PM10, NO2, SO2, CO, O3, AQI
         https://api.openweathermap.org/data/2.5/air_pollution
      2. Current Weather API → temp, humidity, wind_speed, wind_dir
         https://api.openweathermap.org/data/2.5/weather

    Free tier: 1,000 calls/day — enough for all 6 cities at 15-min refresh.
    Sign up:   https://openweathermap.org/api  (free, instant key)

    The returned DataFrame has IDENTICAL columns to what the rest of
    the pipeline expects — no other file needs to change.
    """
    if not api_key:
        logger.warning("No OpenWeather API key — using synthetic data for demo")
        return generate_live_synthetic(city)

    from config.settings import CITIES
    coords = CITIES.get(city.lower())
    if not coords:
        logger.warning(f"Unknown city '{city}' — using synthetic data")
        return generate_live_synthetic(city)

    lat, lon = coords["lat"], coords["lon"]
    OW_BASE  = "https://api.openweathermap.org/data/2.5"

    try:
        # ── 1. Air Pollution (pollutants + AQI) ──────────────
        ap_resp = requests.get(
            f"{OW_BASE}/air_pollution",
            params={"lat": lat, "lon": lon, "appid": api_key},
            timeout=10,
        )
        ap_resp.raise_for_status()
        ap = ap_resp.json()["list"][0]           # most recent reading

        components = ap["components"]
        ow_aqi     = ap["main"]["aqi"]           # 1=Good … 5=Very Poor (OW scale)

        # ── 2. Current Weather (meteorology) ─────────────────
        wx_resp = requests.get(
            f"{OW_BASE}/weather",
            params={"lat": lat, "lon": lon, "appid": api_key, "units": "metric"},
            timeout=10,
        )
        wx_resp.raise_for_status()
        wx = wx_resp.json()

        # ── 3. Build historical window (last 96 × 15-min) ────
        #    OpenWeather free tier returns only the current reading.
        #    We pad back with slight noise so the LSTM gets a proper
        #    48-step sequence — same approach as the synthetic fallback.
        now    = pd.Timestamp.utcnow()
        pm25   = float(components.get("pm2_5", 80))
        pm10   = float(components.get("pm10",  pm25 * 1.8))
        no2    = float(components.get("no2",   pm25 * 0.35))
        so2    = float(components.get("so2",   pm25 * 0.12))
        co     = float(components.get("co",    pm25 * 0.08))
        o3     = float(components.get("o3",    40.0))
        temp   = float(wx["main"]["temp"])
        hum    = float(wx["main"]["humidity"])
        ws     = float(wx["wind"].get("speed", 3.5))
        wd     = float(wx["wind"].get("deg",   180.0))
        pblh   = 800.0   # OpenWeather doesn't expose PBLH; use climatological default

        rows = []
        for i in range(96):
            ts    = now - pd.Timedelta(minutes=15 * (95 - i))
            noise = np.random.lognormal(0, 0.06)    # small realistic jitter
            rows.append({
                "station":   f"{city.title()} (OpenWeather)",
                "lat":        lat,
                "lon":        lon,
                "datetime":   ts,
                "pm25":       round(max(1.0, pm25  * noise), 1),
                "pm10":       round(max(1.0, pm10  * noise), 1),
                "no2":        round(max(0.0, no2   * noise), 1),
                "so2":        round(max(0.0, so2   * noise), 1),
                "co":         round(max(0.0, co    * noise), 2),
                "o3":         round(max(0.0, o3    * noise), 1),
                "temp":       round(temp + np.random.normal(0, 0.3), 1),
                "humidity":   round(min(100, max(0, hum + np.random.normal(0, 1))), 1),
                "wind_speed": round(max(0.1, ws   + np.random.normal(0, 0.2)), 1),
                "wind_dir":   round((wd + np.random.normal(0, 5)) % 360, 0),
                "pblh":       pblh + np.random.normal(0, 30),
                "city":       city.title(),
            })

        df = pd.DataFrame(rows)
        logger.success(
            f"OpenWeather [{city}]: PM2.5={pm25} µg/m³  "
            f"AQI={ow_aqi}  temp={temp}°C  ws={ws} m/s"
        )
        return df

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            logger.error("OpenWeather: Invalid API key. Get one free at openweathermap.org/api")
        else:
            logger.error(f"OpenWeather HTTP error: {e}")
        return generate_live_synthetic(city)

    except Exception as e:
        logger.error(f"OpenWeather error: {e} — falling back to synthetic")
        return generate_live_synthetic(city)


def fetch_openweather_history(city: str, api_key: str,
                               hours_back: int = 120) -> pd.DataFrame:
    """
    Pull historical air pollution data from OpenWeather (paid tier).
    Free tier only gives current; history requires a One Call 3.0 subscription.
    For the hackathon demo, use Kaggle historical + live current reading.

    Endpoint: /data/2.5/air_pollution/history?lat=&lon=&start=&end=&appid=
    """
    from config.settings import CITIES
    coords = CITIES.get(city.lower(), {"lat": 28.6, "lon": 77.2})
    lat, lon = coords["lat"], coords["lon"]

    end_ts   = int(pd.Timestamp.utcnow().timestamp())
    start_ts = end_ts - hours_back * 3600

    try:
        resp = requests.get(
            "https://api.openweathermap.org/data/2.5/air_pollution/history",
            params={
                "lat":   lat, "lon": lon,
                "start": start_ts, "end": end_ts,
                "appid": api_key,
            },
            timeout=15,
        )
        resp.raise_for_status()
        records = []
        for entry in resp.json().get("list", []):
            c = entry["components"]
            records.append({
                "timestamp":  pd.Timestamp.utcfromtimestamp(entry["dt"]),
                "pm25":       c.get("pm2_5", np.nan),
                "pm10":       c.get("pm10",  np.nan),
                "no2":        c.get("no2",   np.nan),
                "so2":        c.get("so2",   np.nan),
                "co":         c.get("co",    np.nan),
                "o3":         c.get("o3",    np.nan),
                "city":       city.title(),
            })
        return pd.DataFrame(records)

    except Exception as e:
        logger.warning(f"OpenWeather history unavailable: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────
# 3. GOOGLE EARTH ENGINE — Sentinel-5P NO2/SO2
# ─────────────────────────────────────────────────────────
def download_sentinel5p(city: str, start: str, end: str, save_path: Path):
    """
    Pull Sentinel-5P NO2 column from GEE.
    Requires: earthengine-api + authenticated GEE project.

    Usage:
        import ee; ee.Initialize(project='your-project')
        download_sentinel5p('delhi', '2024-01-01', '2024-03-31', Path('data/raw/sentinel'))
    """
    try:
        import ee
        ee.Initialize()

        from config.settings import CITIES
        coords = CITIES[city.lower()]

        point = ee.Geometry.Point([coords["lon"], coords["lat"]])
        bbox  = point.buffer(50000).bounds()   # 50 km radius

        collection = (
            ee.ImageCollection("COPERNICUS/S5P/NRTI/L3_NO2")
            .filterDate(start, end)
            .filterBounds(bbox)
            .select("tropospheric_NO2_column_number_density")
            .mean()
        )

        task = ee.batch.Export.image.toDrive(
            image       = collection,
            description = f"sentinel5p_no2_{city}",
            scale       = 1000,
            region      = bbox,
            fileFormat  = "GeoTIFF",
        )
        task.start()
        logger.info(f"GEE export started for {city}. Check Google Drive.")

    except ImportError:
        logger.warning("earthengine-api not installed — skipping GEE download")
    except Exception as e:
        logger.error(f"GEE error: {e}")


# ─────────────────────────────────────────────────────────
# 4. SYNTHETIC DATA GENERATOR (for local demo / no API keys)
# ─────────────────────────────────────────────────────────
import numpy as np

def create_synthetic_aqi_data(out_dir: Path, name: str):
    """
    Creates realistic synthetic AQI data for demo purposes.
    Mimics real OpenWeather / urban AQI patterns: seasonal cycles, rush-hour peaks,
    Diwali spikes, monsoon dips, city-level baseline differences.
    """
    logger.info(f"Generating synthetic AQI data → {out_dir}")
    np.random.seed(42)

    cities = ["Delhi", "Mumbai", "Bengaluru", "Kolkata", "Chennai", "Hyderabad"]
    # city baseline PM2.5 (Delhi most polluted, Bengaluru cleanest)
    baselines = {"Delhi": 110, "Mumbai": 65, "Bengaluru": 40,
                 "Kolkata": 85, "Chennai": 55, "Hyderabad": 60}
    pollutants = ["pm25", "pm10", "no2", "so2", "co", "o3"]

    records = []
    dates = pd.date_range("2015-01-01", "2024-12-31", freq="h")

    for city in cities:
        base = baselines[city]
        for dt in dates[::4]:   # every 4 hours (lightweight)
            # Seasonal cycle: worse in winter (Oct–Feb)
            month_factor = 1.0 + 0.6 * np.cos((dt.month - 1) * 2 * np.pi / 12)
            # Diurnal cycle: rush hours 8am, 6pm
            hour_factor = 1.0 + 0.3 * (
                np.exp(-((dt.hour - 8) ** 2) / 8) +
                np.exp(-((dt.hour - 18) ** 2) / 8)
            )
            # Diwali spike (mid-Oct to early Nov)
            diwali = 1.0 + (2.5 if (dt.month == 10 and dt.day > 20) or
                           (dt.month == 11 and dt.day < 5) else 0)
            # Monsoon suppression (Jun–Sep)
            monsoon = 0.45 if 6 <= dt.month <= 9 else 1.0
            # Random noise
            noise = np.random.lognormal(0, 0.18)

            pm25 = max(5, base * month_factor * hour_factor * diwali * monsoon * noise)
            pm10 = pm25 * np.random.uniform(1.5, 2.2)

            records.append({
                "city":      city,
                "datetime":  dt,
                "pm25":      round(pm25, 1),
                "pm10":      round(pm10, 1),
                "no2":       round(pm25 * 0.35 * np.random.uniform(0.8, 1.2), 1),
                "so2":       round(pm25 * 0.12 * np.random.uniform(0.7, 1.3), 1),
                "co":        round(pm25 * 0.08 * np.random.uniform(0.9, 1.1), 2),
                "o3":        round(40 * hour_factor * monsoon * noise, 1),
                "temp":      round(25 + 8 * np.sin((dt.month - 4) * np.pi / 6) +
                                   np.random.normal(0, 2), 1),
                "humidity":  round(min(100, max(20, 60 + 20 * monsoon +
                                   np.random.normal(0, 8))), 1),
                "wind_speed": round(max(0.1, np.random.exponential(3.5)), 1),
                "wind_dir":  round(np.random.uniform(0, 360), 0),
                "pblh":      round(800 + 600 * np.sin((dt.hour - 6) * np.pi / 12) +
                                   np.random.normal(0, 100), 0),
            })

    df = pd.DataFrame(records)
    df.to_csv(out_dir / "city_aqi_hourly.csv", index=False)
    logger.success(f"  ✓ {len(df):,} rows synthetic AQI data saved")
    return df


def generate_live_synthetic(city: str) -> pd.DataFrame:
    """Single-city live reading for API demo fallback."""
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    base = {"delhi": 110, "mumbai": 65, "bengaluru": 40}.get(city.lower(), 75)
    records = []
    for i in range(96):  # last 24 hours, 15-min intervals
        ts = now - timedelta(minutes=15 * (95 - i))
        noise = np.random.lognormal(0, 0.15)
        pm25 = max(5, base * noise)
        records.append({
            "station":    f"{city.title()} Central",
            "lat":        28.6 if city.lower() == "delhi" else 19.0,
            "lon":        77.2 if city.lower() == "delhi" else 72.8,
            "datetime":   ts,
            "city":       city.title(),
            "pm25":       round(pm25, 1),
            "pm10":       round(pm25 * 1.8, 1),
            "no2":        round(pm25 * 0.35, 1),
            "so2":        round(pm25 * 0.12, 1),
            "co":         round(pm25 * 0.08, 2),
            "o3":         round(pm25 * 0.6, 1),
            "temp":       round(25 + np.random.normal(0, 0.5), 1),
            "humidity":   round(min(100, max(0, 60 + np.random.normal(0, 2))), 1),
            "wind_speed": round(max(0.1, 3.5 + np.random.normal(0, 0.3)), 1),
            "wind_dir":   round((180 + np.random.normal(0, 10)) % 360, 0),
            "pblh":       800.0 + np.random.normal(0, 30),
        })
    return pd.DataFrame(records)


# ─────────────────────────────────────────────────────────
# 5. SOURCE LABEL GENERATOR (for attribution model training)
# ─────────────────────────────────────────────────────────
def create_source_attribution_labels(aqi_df: pd.DataFrame) -> pd.DataFrame:
    """
    Creates synthetic source-contribution labels for training
    the XGBoost attribution model.

    In production: replace with actual OpenWeather + receptor-model studies
    (CMB/PMF) from cities with completed source apportionment.
    Reference: urbanemissions.info source apportionment data
    """
    np.random.seed(99)
    n = len(aqi_df)

    # City-level source profiles (from published OpenWeather / urban emission studies)
    city_profiles = {
        "Delhi":     [0.38, 0.20, 0.18, 0.14, 0.10],
        "Mumbai":    [0.30, 0.25, 0.22, 0.10, 0.13],
        "Bengaluru": [0.45, 0.18, 0.15, 0.08, 0.14],
        "Kolkata":   [0.28, 0.18, 0.26, 0.18, 0.10],
        "Chennai":   [0.40, 0.20, 0.20, 0.10, 0.10],
        "Hyderabad": [0.35, 0.22, 0.20, 0.12, 0.11],
    }
    # Sources: vehicle, construction, industrial, biomass, secondary

    contributions = []
    for _, row in aqi_df.iterrows():
        city  = row.get("city", "Delhi")
        base  = city_profiles.get(city, city_profiles["Delhi"])
        # Add noise + seasonal patterns
        month = pd.to_datetime(row.get("datetime", "2020-01-01")).month
        biomass_boost = 0.12 if (month in [10, 11, 4]) else 0.0  # crop burning
        profile = base.copy()
        profile[3] += biomass_boost
        profile = [max(0, p + np.random.normal(0, 0.04)) for p in profile]
        total = sum(profile)
        profile = [p / total for p in profile]
        contributions.append(profile)

    contrib_df = pd.DataFrame(contributions,
        columns=["src_vehicle", "src_construction", "src_industrial",
                 "src_biomass", "src_secondary"])
    return pd.concat([aqi_df.reset_index(drop=True), contrib_df], axis=1)


# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("═══ VAYU Data Download ═══")
    download_kaggle_datasets()
    logger.success("Data download complete. Run: python data/preprocess.py")