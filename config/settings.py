# config/settings.py
# ─────────────────────────────────────────────────────────
# VAYU — Central Configuration
# Copy .env.example (or .enc.example) to .env and fill in your keys
# ─────────────────────────────────────────────────────────

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Project Paths ─────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent
DATA_DIR   = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models" / "saved"
LOGS_DIR   = BASE_DIR / "logs"

for d in [DATA_DIR, MODELS_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── API Keys (set in .env) ────────────────────────────────
GROQ_API_KEY        = os.getenv("GROQ_API_KEY", "")         # console.groq.com — free
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")   # openweathermap.org/api (weather)
WAQI_API_KEY        = os.getenv("WAQI_API_KEY", "")           # aqicn.org/data-platform/token (pollutants)
GEE_PROJECT         = os.getenv("GEE_PROJECT", "")           # Google Earth Engine (optional)
TWILIO_SID         = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN       = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_NO = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
OPENWEATHER_KEY    = os.getenv("OPENWEATHER_API_KEY", "")

# ── Supabase (replaces local PostgreSQL / SQLite) ─────────
SUPABASE_URL         = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY    = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# ── Cities covered ────────────────────────────────────────
CITIES = {
    "delhi":     {"lat": 28.6139, "lon": 77.2090, "state": "Delhi"},
    "mumbai":    {"lat": 19.0760, "lon": 72.8777, "state": "Maharashtra"},
    "bengaluru": {"lat": 12.9716, "lon": 77.5946, "state": "Karnataka"},
    "kolkata":   {"lat": 22.5726, "lon": 88.3639, "state": "West Bengal"},
    "chennai":   {"lat": 13.0827, "lon": 80.2707, "state": "Tamil Nadu"},
    "hyderabad": {"lat": 17.3850, "lon": 78.4867, "state": "Telangana"},
}

# ── Pollutants tracked ────────────────────────────────────
POLLUTANTS = ["pm25", "pm10", "no2", "so2", "co", "o3"]

# ── AQI display bands (WAQI / US EPA scale) ───────────────
AQI_BREAKPOINTS = {
    "pm25": [
        (0,    30,   0,   50,  "Good"),
        (30,   60,   51,  100, "Satisfactory"),
        (60,   90,   101, 200, "Moderate"),
        (90,   120,  201, 300, "Poor"),
        (120,  250,  301, 400, "Very Poor"),
        (250,  500,  401, 500, "Severe"),
    ],
    "pm10": [
        (0,    50,   0,   50,  "Good"),
        (50,   100,  51,  100, "Satisfactory"),
        (100,  250,  101, 200, "Moderate"),
        (250,  350,  201, 300, "Poor"),
        (350,  430,  301, 400, "Very Poor"),
        (430,  600,  401, 500, "Severe"),
    ],
}

# ── Model Hyperparameters ─────────────────────────────────
FORECAST_CONFIG = {
    "sequence_len":   48,          # KEEP
    "forecast_len":   192,         # KEEP if you need 48h forecast

    "hidden_size":    256,         # CHANGE from 256 -> 192
    "num_layers":     2,           # CHANGE from 3 -> 2
    "dropout":        0.15,

    "batch_size":     128,         # CHANGE from 64 -> 256
    "epochs":         20,          # CHANGE from 50 -> 20
    "lr":             5e-4,
    "early_stop":     7,           # CHANGE from 7 -> 3

    "features":       POLLUTANTS + [
        "temp",
        "humidity",
        "wind_speed",
        "wind_dir",
        "pblh"
    ],

    "num_workers":    8,           # CHANGE from 4 -> 8
    "use_amp":        True,
    "compile_model":  False,       # CHANGE to False for now
}

ATTRIBUTION_CONFIG = {
    "n_estimators":   500,
    "max_depth":      8,
    "learning_rate":  0.05,
    "subsample":      0.8,
    "colsample":      0.8,
    "sources":        ["vehicle", "construction", "industrial", "biomass", "secondary"],
}

# ── H3 Spatial Resolution ────────────────────────────────
H3_RESOLUTION = 8    # ~460m hexagons ≈ ward level

# ── Update Intervals ──────────────────────────────────────
CAAQMS_INTERVAL_MIN   = 15
FORECAST_INTERVAL_MIN = 60
SATELLITE_INTERVAL_HR = 24
