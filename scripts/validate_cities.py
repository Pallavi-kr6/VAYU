"""Run validation across all 6 cities (requires OPENWEATHER_API_KEY + WAQI_API_KEY)."""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from config.settings import OPENWEATHER_API_KEY, WAQI_API_KEY, CITIES
from data.download_data import fetch_openweather_live
from data.preprocess import engineer_features
from models.train_attribution import AttributionInference
from models.train_forecast import ForecastInference
from data.enforcement_assets import get_enforcement_assets

ai = AttributionInference()
fi = ForecastInference()
print("Models loaded OK\n")

report = []
for city in CITIES:
    raw, meta = fetch_openweather_live(
        city, api_key=OPENWEATHER_API_KEY, waqi_api_key=WAQI_API_KEY,
    )
    feat = engineer_features(raw)
    attr = ai.predict(feat)
    fc = fi.predict(raw, n_steps=48)
    enf = get_enforcement_assets(city)
    top_enf = enf[0]["name"] if enf else "NONE"
    report.append({
        "city": city,
        "source": meta.get("pollution_source"),
        "pm25": meta["pm25_ug_m3"],
        "waqi_aqi": meta["aqi"],
        "conf": attr["overall_confidence"],
        "dominant": attr["dominant_source"],
        "fc_peak_aqi": int(fc["aqi_pred"].max()),
        "fc_peak_pm25": float(fc["pm25_pred"].max()),
        "enforcement_top": top_enf[:45],
    })

print("=" * 90)
print("VAYU VALIDATION REPORT (WAQI + OpenWeather weather)")
print("=" * 90)
for r in report:
    print(
        f"{r['city']:12} src={r['source']:10} PM2.5={r['pm25']:6.1f} "
        f"WAQI={r['waqi_aqi']:3} conf={r['conf']:.2f} peak_fc={r['fc_peak_aqi']:3} "
        f"enf={r['enforcement_top']}"
    )

confs = [r["conf"] for r in report]
print(f"\nConfidence: min={min(confs):.2f} max={max(confs):.2f}")
print(f"Unique enforcement tops: {len(set(r['enforcement_top'] for r in report))}/6")
