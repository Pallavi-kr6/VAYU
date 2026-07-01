# api/main.py
# ─────────────────────────────────────────────────────────
# VAYU FastAPI Backend
# Endpoints:
#   GET  /api/cities                    — list of cities
#   GET  /api/attribution/{city}        — source attribution
#   GET  /api/forecast/{city}           — 48h AQI forecast
#   GET  /api/enforcement/{city}        — enforcement action queue
#   GET  /api/advisory/{city}           — citizen health advisory
#   GET  /api/dashboard/{city}          — all-in-one dashboard data
#   GET  /api/comparative               — multi-city comparison
#   POST /api/chatbot                   — citizen WhatsApp chatbot
#   POST /api/webhook/whatsapp          — Twilio incoming webhook
# ─────────────────────────────────────────────────────────

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import pandas as pd
import numpy as np
from datetime import datetime
from loguru import logger

from config.settings import CITIES
from agents.vayu_agents import (
    VAYUOrchestrator, BUS, CitizenHealthShieldAgent
)
from data.download_data import fetch_openweather_live
from services.geospatial_service import GeoSpatialService

# ─── App setup ────────────────────────────────────────────
app = FastAPI(
    title       = "VAYU — Urban Air Quality Intelligence API",
    description = "ET AI Hackathon 2026 | Problem #5",
    version     = "1.0.0",
    docs_url    = "/docs",
    redoc_url   = "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials = False,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ─── Global orchestrator (loaded once at startup) ─────────
orchestrator: Optional[VAYUOrchestrator] = None
citizen_agent: Optional[CitizenHealthShieldAgent] = None
_last_run: dict = {}   # tracks when each city was last updated


@app.on_event("startup")
async def startup():
    global orchestrator, citizen_agent
    logger.info("VAYU API starting up...")
    orchestrator  = VAYUOrchestrator()
    citizen_agent = orchestrator.citizen_agent
    # Pre-warm all 6 cities with synthetic data
    for city in CITIES:
        await _refresh_city(city)
    logger.info("✓ All cities pre-warmed")


# ─── Helper: refresh pipeline for a city ─────────────────
async def _refresh_city(city: str):
    """Pulls latest OpenWeather data, engineers features, runs agent pipeline."""
    global _last_run
    from config.settings import OPENWEATHER_API_KEY, WAQI_API_KEY
    from data.preprocess import engineer_features

    raw_df, live_meta = fetch_openweather_live(
        city, api_key=OPENWEATHER_API_KEY, waqi_api_key=WAQI_API_KEY,
    )
    BUS.set(f"live_{city}", live_meta)

    now_iso = live_meta.get("fetched_at", datetime.utcnow().isoformat())
    point = {
        "datetime": now_iso,
        "pm25":     float(live_meta.get("pm25_ug_m3", 0)),
        "pm10":     float(live_meta.get("pm10_ug_m3", 0)),
        "aqi":      int(live_meta.get("aqi", 0)),
    }
    prior = BUS.get(f"history_{city}") or []
    if not prior or prior[-1].get("datetime") != point["datetime"]:
        prior.append(point)
    BUS.set(f"history_{city}", prior[-96:])

    df = engineer_features(raw_df)
    BUS.set(f"features_{city}", {
        "columns": list(df.columns),
        "row_count": len(df),
        "sample_last": df.iloc[-1].to_dict() if len(df) else {},
    })

    orchestrator.run_city(city, df)
    _last_run[city] = datetime.utcnow().isoformat()


# ════════════════════════════════════════════════════════
# ROUTES
# ════════════════════════════════════════════════════════

@app.get("/")
def root():
    return {
        "name":    "VAYU Air Quality Intelligence API",
        "version": "1.0.0",
        "docs":    "/docs",
        "cities":  list(CITIES.keys()),
    }


@app.get("/api/cities")
def get_cities():
    """List all supported cities with metadata."""
    return {
        "cities": [
            {
                "id":    city,
                "name":  info["state"] + " / " + city.title(),
                "lat":   info["lat"],
                "lon":   info["lon"],
                "state": info["state"],
            }
            for city, info in CITIES.items()
        ]
    }


@app.get("/api/attribution/{city}")
async def get_attribution(city: str, refresh: bool = False):
    """
    Get source attribution for a city.
    refresh=true forces a new model run (use sparingly).
    """
    city = city.lower()
    if city not in CITIES:
        raise HTTPException(404, f"City '{city}' not supported")

    if refresh or BUS.get(f"attribution_{city}") is None:
        await _refresh_city(city)

    data = BUS.get(f"attribution_{city}")
    if not data:
        raise HTTPException(503, "Attribution data not yet available")
    return data


@app.get("/api/forecast/{city}")
async def get_forecast(city: str, hours: int = 48):
    """
    Get AQI forecast for next N hours (max 72).
    Returns 15-minute interval predictions.
    """
    city  = city.lower()
    hours = min(hours, 72)

    if city not in CITIES:
        raise HTTPException(404, f"City '{city}' not supported")

    if BUS.get(f"forecast_{city}") is None:
        await _refresh_city(city)

    fc_all = BUS.get(f"forecast_{city}") or []
    n_steps = hours * 4
    fc      = fc_all[:n_steps]

    # Hourly summary (aggregate 4 × 15-min to 1h)
    fc_df = pd.DataFrame(fc)
    if not fc_df.empty and "hours_ahead" in fc_df:
        fc_df["hour_bucket"] = (fc_df["hours_ahead"]).apply(lambda x: int(x) + 1)
        hourly = fc_df.groupby("hour_bucket").agg(
            hours_ahead  = ("hours_ahead", "max"),
            pm25_mean    = ("pm25_pred", "mean"),
            pm25_max     = ("pm25_pred", "max"),
            aqi_max      = ("aqi_pred",  "max"),
            aqi_category = ("aqi_category", lambda x: x.mode()[0] if len(x) else "Moderate"),
        ).reset_index(drop=True)
        hourly_records = hourly.round(1).to_dict(orient="records")
    else:
        hourly_records = []

    return {
        "city":         city,
        "hours":        hours,
        "interval_15m": fc,
        "hourly":       hourly_records,
        "generated_at": _last_run.get(city, "unknown"),
    }


@app.get("/api/enforcement/{city}")
async def get_enforcement(city: str):
    """
    Get ranked enforcement action queue for inspectors.
    """
    city = city.lower()
    if city not in CITIES:
        raise HTTPException(404, f"City '{city}' not supported")

    if BUS.get(f"enforcement_{city}") is None:
        await _refresh_city(city)

    data = BUS.get(f"enforcement_{city}") or []
    return {
        "city":    city,
        "actions": data,
        "count":   len(data),
        "message": None if data else f"No enforcement assets registered for {city}.",
        "generated_at": _last_run.get(city, "unknown"),
    }


@app.get("/api/advisory/{city}")
async def get_advisory(
    city: str,
    language: str = None,
    ward: str = None,
    vulnerable: bool = False,
):
    """
    Get personalised citizen health advisory.
    language: ISO code (hi, en, ta, kn, bn, mr, te, gu, ml, pa, or, ur)
    """
    city = city.lower()
    if city not in CITIES:
        raise HTTPException(404, f"City '{city}' not supported")

    if BUS.get(f"forecast_{city}") is None:
        await _refresh_city(city)

    profile  = {"language": language, "ward": ward, "vulnerable": vulnerable}
    advisory = citizen_agent.generate_advisory(city, profile)
    return advisory


@app.get("/api/dashboard/{city}")
async def get_dashboard(city: str):
    """
    All-in-one dashboard data: attribution + forecast + enforcement + advisory.
    Single call for the frontend.
    """
    city = city.lower()
    if city not in CITIES:
        raise HTTPException(404, f"City '{city}' not supported")

    if BUS.get(f"attribution_{city}") is None:
        await _refresh_city(city)

    attr = BUS.get(f"attribution_{city}") or {}
    fc_all = BUS.get(f"forecast_{city}") or []
    fc   = fc_all[:48]
    enf  = (BUS.get(f"enforcement_{city}") or [])[:5]
    adv  = BUS.get(f"citizen_advisory_{city}") or {}
    live = BUS.get(f"live_{city}") or {}

    hist_trend = BUS.get(f"history_{city}") or []

    return {
        "city":           city,
        "city_info":      CITIES[city],
        "last_updated":   _last_run.get(city, datetime.utcnow().isoformat()),
        "live_api":       live,
        "attribution":    attr,
        "forecast_12h":   fc,
        "forecast_48h":   fc_all[:192],
        "enforcement":    enf,
        "advisory":       adv,
        "historical_trend": hist_trend,
        "summary": {
            "current_pm25":     attr.get("current_pm25"),
            "current_aqi":      attr.get("current_aqi"),
            "aqi_category":     attr.get("aqi_category") or _aqi_to_cat(attr.get("current_aqi", 0)),
            "aqi_source":       attr.get("aqi_source", "waqi"),
            "aqi_label":        attr.get("aqi_label", "Live AQI (WAQI)"),
            "pollution_source": live.get("pollution_source"),
            "waqi":             live.get("waqi"),
            "dominant_source":  attr.get("dominant_source"),
            "confidence":       attr.get("overall_confidence"),
            "pending_actions":  len(enf),
        },
    }


@app.get("/api/comparative")
async def get_comparative(refresh: bool = False):
    """Multi-city comparison for command centre view."""
    if refresh or BUS.get("multi_city_report") is None:
        for city in CITIES:
            if BUS.get(f"attribution_{city}") is None:
                await _refresh_city(city)
        orchestrator.comparative_agent.run()

    return BUS.get("multi_city_report") or {"error": "No comparative data yet"}


@app.get("/geospatial-insights")
async def get_geospatial_insights(lat: float, lon: float):
    """Optional geospatial intelligence layer for location-based risk insights."""
    try:
        service = GeoSpatialService()
        insights = service.get_insights(lat, lon)
        return {"status": "ok", "data": insights}
    except Exception as exc:
        logger.warning("Geospatial insights failed: %s", exc)
        return {
            "status": "fallback",
            "data": {
                "location": {"lat": lat, "lon": lon},
                "insights": {
                    "vegetation_index": 0.0,
                    "fire_hotspots": [],
                    "land_use": {"type": "FeatureCollection", "features": []},
                    "pollution_risk_factors": {
                        "vehicular": 0.0,
                        "industrial": 0.0,
                        "biomass": 0.0,
                    },
                },
                "confidence_score": 0.0,
            },
            "message": str(exc),
        }


# ─── Chatbot ──────────────────────────────────────────────
class ChatRequest(BaseModel):
    message:  str
    city:     str = "delhi"
    language: Optional[str] = None
    phone:    Optional[str] = None

@app.post("/api/chatbot")
async def chatbot(req: ChatRequest):
    """
    Citizen chatbot endpoint.
    Accepts a question in any Indian language, returns AQI advisory.
    """
    city = req.city.lower()
    if city not in CITIES:
        city = "delhi"

    if BUS.get(f"forecast_{city}") is None:
        await _refresh_city(city)

    reply = citizen_agent.handle_chatbot_query(req.message, city, req.phone)
    return {
        "reply":  reply,
        "city":   city,
        "status": "ok",
    }


# ─── Twilio WhatsApp Webhook ──────────────────────────────
from fastapi import Form

@app.post("/api/webhook/whatsapp")
async def whatsapp_webhook(
    Body: str = Form(...),
    From: str = Form(...),
    background_tasks: BackgroundTasks = None,
):
    """
    Twilio sends incoming WhatsApp messages here.
    Configure in Twilio Console:
        Webhook URL: https://your-domain.com/api/webhook/whatsapp
        Method: HTTP POST
    """
    message  = Body.strip()
    phone    = From  # e.g. 'whatsapp:+919876543210'

    # Detect city from message (simple keyword matching)
    city = "delhi"
    for c in CITIES:
        if c in message.lower():
            city = c
            break

    logger.info(f"WhatsApp from {phone}: {message[:60]}...")

    if BUS.get(f"forecast_{city}") is None:
        await _refresh_city(city)

    reply = citizen_agent.handle_chatbot_query(message, city, phone=None)
    citizen_agent.send_whatsapp(phone, reply)

    # Twilio expects TwiML response (empty is fine when using send separately)
    return JSONResponse(
        content = {"status": "ok"},
        headers = {"Content-Type": "application/json"}
    )


@app.get("/api/debug/{city}")
async def debug_city(city: str):
    """
    Diagnostics: data lineage from OpenWeather API + trained models.
    """
    city = city.lower()
    if city not in CITIES:
        raise HTTPException(404, f"City '{city}' not supported")

    if BUS.get(f"attribution_{city}") is None:
        await _refresh_city(city)

    attr = BUS.get(f"attribution_{city}") or {}
    fc   = BUS.get(f"forecast_{city}") or []
    enf  = BUS.get(f"enforcement_{city}") or []
    live = BUS.get(f"live_{city}") or {}
    feat = BUS.get(f"features_{city}") or {}

    return {
        "city":              city,
        "timestamp":         datetime.utcnow().isoformat(),
        "live_api_data":     live,
        "derived_features":  feat,
        "attribution_output": attr,
        "forecast_output":   fc[:24],
        "enforcement_output": enf,
        "confidence_scores": {
            "attribution_overall": attr.get("overall_confidence"),
            "attribution_method":  attr.get("confidence_method"),
            "per_source_pct":      {s["label"]: s["pct"] for s in attr.get("sources", [])},
        },
        "models": {
            "attribution": "AttributionInference (XGBoost)",
            "forecast":    "ForecastInference (BiLSTM)",
        },
        "data_lineage": {
            "pm25":        "WAQI API (fallback: OpenWeather Air Pollution) → engineer_features → models",
            "aqi":         "WAQI live index (US EPA scale 0–500)",
            "weather":     "OpenWeather Weather API → temp, humidity, wind, pressure, rain",
            "forecast":    "LSTM PM2.5 → scaled from live WAQI AQI",
            "enforcement": "city enforcement_assets + attribution scores",
        },
    }


# ─── Health check ─────────────────────────────────────────
@app.get("/health")
def health():
    from db.supabase_store import SupabaseStore
    return {
        "status":        "ok",
        "timestamp":     datetime.utcnow().isoformat(),
        "cities_warmed": [c for c in CITIES if BUS.get(f"attribution_{c}")],
        "supabase":      SupabaseStore.is_configured(),
    }


# ─── Helper ───────────────────────────────────────────────
def _aqi_to_cat(aqi: int) -> str:
    if aqi <= 50:   return "Good"
    if aqi <= 100:  return "Satisfactory"
    if aqi <= 200:  return "Moderate"
    if aqi <= 300:  return "Poor"
    if aqi <= 400:  return "Very Poor"
    return "Severe"


# ─── Run directly ─────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
