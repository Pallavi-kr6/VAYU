# agents/vayu_agents.py
# ─────────────────────────────────────────────────────────
# VAYU Multi-Agent System — 5 specialized AI agents
# LLM backend: Groq (llama-3.3-70b-versatile) — free, fast
# ─────────────────────────────────────────────────────────

import sys, json, asyncio, re
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from datetime import datetime, timedelta
from typing import Optional
import pandas as pd
import numpy as np
from loguru import logger
import groq as groq_lib

from config.settings import (
    GROQ_API_KEY, CITIES, POLLUTANTS,
    TWILIO_SID, TWILIO_TOKEN, TWILIO_WHATSAPP_NO
)

# ── Lazy-load ML models (only if trained files exist)
def _load_attribution():
    try:
        from models.train_attribution import AttributionInference
        return AttributionInference()
    except Exception as e:
        logger.warning(f"Attribution model not loaded: {e} — using mock")
        return None

def _load_forecast():
    try:
        from models.train_forecast import ForecastInference
        return ForecastInference()
    except Exception as e:
        logger.warning(f"Forecast model not loaded: {e} — using mock")
        return None

# ── Groq client (single instance reused by all agents)
groq_client = groq_lib.Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
GROQ_MODEL  = "llama-3.3-70b-versatile"

def _groq_chat(system: str, user: str, max_tokens: int = 300) -> str:
    """
    Thin wrapper around Groq chat completions.
    Returns the assistant text, or raises so callers can fallback.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    resp = groq_client.chat.completions.create(
        model      = GROQ_MODEL,
        messages   = messages,
        temperature= 0.2,
        max_tokens = max_tokens,
    )
    return resp.choices[0].message.content


# ════════════════════════════════════════════════════════
# CENTRAL INTELLIGENCE BUS
# ════════════════════════════════════════════════════════
class IntelligenceBus:
    def __init__(self):
        self._store: dict = {}
        self._hydrate_from_supabase()

    def _hydrate_from_supabase(self):
        from db.supabase_store import SupabaseStore
        if not SupabaseStore.is_configured():
            return
        cached = SupabaseStore.load_all()
        if cached:
            self._store.update(cached)
            logger.info(f"IntelligenceBus hydrated {len(cached)} keys from Supabase")

    def set(self, key: str, value):
        self._store[key] = {"data": value, "updated": datetime.utcnow().isoformat()}
        from db.supabase_store import SupabaseStore
        SupabaseStore.set(key, value)

    def get(self, key: str):
        entry = self._store.get(key)
        if entry:
            return entry["data"]
        from db.supabase_store import SupabaseStore
        data = SupabaseStore.get(key)
        if data is not None:
            self._store[key] = {"data": data, "updated": datetime.utcnow().isoformat()}
            return data
        return None

    def get_all(self) -> dict:
        return {k: v["data"] for k, v in self._store.items()}


BUS = IntelligenceBus()


# ════════════════════════════════════════════════════════
# AGENT 1 — SOURCE ATTRIBUTION AGENT
# ════════════════════════════════════════════════════════
class SourceAttributionAgent:
    def __init__(self):
        self.model = _load_attribution()
        logger.info("SourceAttributionAgent initialized")

    def run(self, city: str, recent_df: pd.DataFrame) -> dict:
        logger.info(f"[AttributionAgent] Running for {city}...")

        if self.model:
            result = self.model.predict(recent_df)
        else:
            result = self._mock_attribution(city, recent_df)

        result["city"]        = city
        result["timestamp"]   = datetime.utcnow().isoformat()
        result["current_pm25"] = float(
            recent_df["pm25"].iloc[-1] if "pm25" in recent_df else 85.0
        )
        result["current_aqi"] = self._pm25_to_aqi(result["current_pm25"])

        BUS.set(f"attribution_{city}", result)
        from db.supabase_store import SupabaseStore
        SupabaseStore.save_reading(
            city=city,
            pm25=result["current_pm25"],
            pm10=result["current_pm25"] * 1.8,
            aqi=result["current_aqi"],
            pollutants={"dominant_source": result.get("dominant_source")},
        )
        logger.info(f"  Dominant: {result['dominant_source']} "
                    f"({result['sources'][0]['pct']}%)  "
                    f"Confidence: {result['overall_confidence']}")
        return result

    def _mock_attribution(self, city: str, df: pd.DataFrame) -> dict:
        month   = datetime.utcnow().month
        biomass = 0.20 if month in [10, 11] else 0.10
        vehicle = 0.38 - (biomass - 0.10) * 0.5
        return {
            "sources": [
                {"source": "src_vehicle",      "label": "Vehicle Exhaust",    "pct": round(vehicle * 100, 1), "color": "#EF4444"},
                {"source": "src_construction", "label": "Construction Dust",  "pct": 22.0,                    "color": "#F59E0B"},
                {"source": "src_industrial",   "label": "Industrial Stacks",  "pct": 18.0,                    "color": "#065A82"},
                {"source": "src_biomass",      "label": "Biomass Burning",    "pct": round(biomass * 100, 1), "color": "#10B981"},
                {"source": "src_secondary",    "label": "Secondary Aerosols", "pct": 10.0,                    "color": "#0D9488"},
            ],
            "overall_confidence": 0.88,
            "dominant_source":    "Vehicle Exhaust",
        }

    @staticmethod
    def _pm25_to_aqi(pm25: float) -> int:
        bps = [(0,30,0,50),(30,60,51,100),(60,90,101,200),
               (90,120,201,300),(120,250,301,400),(250,500,401,500)]
        for lo_c, hi_c, lo_i, hi_i in bps:
            if lo_c <= pm25 <= hi_c:
                return round((hi_i - lo_i) / (hi_c - lo_c) * (pm25 - lo_c) + lo_i)
        return 500


# ════════════════════════════════════════════════════════
# AGENT 2 — PREDICTIVE AQI AGENT
# ════════════════════════════════════════════════════════
class PredictiveAQIAgent:
    def __init__(self):
        self.model = _load_forecast()
        logger.info("PredictiveAQIAgent initialized")

    def run(self, city: str, recent_df: pd.DataFrame, hours: int = 48) -> pd.DataFrame:
        logger.info(f"[ForecastAgent] Generating {hours}h forecast for {city}...")

        if self.model:
            forecast = self.model.predict(recent_df, n_steps=hours * 4)
        else:
            forecast = self._mock_forecast(city, recent_df, hours)

        BUS.set(f"forecast_{city}", forecast.to_dict(orient="records"))
        peak_idx = forecast["aqi_pred"].idxmax()
        peak_row = forecast.iloc[peak_idx]
        logger.info(f"  Peak AQI {peak_row['aqi_pred']:.0f} "
                    f"({peak_row['aqi_category']}) at +{peak_row['hours_ahead']:.1f}h")
        return forecast

    def _mock_forecast(self, city: str, df: pd.DataFrame, hours: int = 48) -> pd.DataFrame:
        base_pm25 = float(df["pm25"].mean()) if "pm25" in df else 90.0
        records = []
        for h in range(1, hours + 1):
            for q in range(4):
                t           = h - 1 + q * 0.25
                hour_of_day = (datetime.utcnow().hour + t) % 24
                factor      = 1 + 0.3 * (
                    np.exp(-((hour_of_day - 8) ** 2) / 8) +
                    np.exp(-((hour_of_day - 18) ** 2) / 8)
                )
                pm25 = max(5, base_pm25 * factor * np.random.lognormal(0, 0.1))
                aqi  = SourceAttributionAgent._pm25_to_aqi(pm25)
                records.append({
                    "step_15min":   len(records) + 1,
                    "hours_ahead":  round(t + 0.25, 2),
                    "pm25_pred":    round(pm25, 1),
                    "aqi_pred":     aqi,
                    "aqi_category": self._aqi_to_cat(aqi),
                })
        return pd.DataFrame(records)

    @staticmethod
    def _aqi_to_cat(aqi: int) -> str:
        if aqi <= 50:   return "Good"
        if aqi <= 100:  return "Satisfactory"
        if aqi <= 200:  return "Moderate"
        if aqi <= 300:  return "Poor"
        if aqi <= 400:  return "Very Poor"
        return "Severe"


# ════════════════════════════════════════════════════════
# AGENT 3 — ENFORCEMENT INTELLIGENCE AGENT
# ════════════════════════════════════════════════════════
class EnforcementAgent:
    POLLUTER_DB = [
        {"id": "IND001", "name": "Bharat Steel Rolling Mill",      "type": "industrial",   "lat": 28.63, "lon": 77.21, "violations": 3, "last_check": "2025-11-10"},
        {"id": "CON001", "name": "Apex Infrastructure Site A",     "type": "construction", "lat": 28.61, "lon": 77.19, "violations": 1, "last_check": "2025-12-01"},
        {"id": "CON002", "name": "DDA Housing Project Sector 9",   "type": "construction", "lat": 28.65, "lon": 77.22, "violations": 2, "last_check": "2025-10-15"},
        {"id": "VEH001", "name": "Old Diesel Bus Depot Anand Vihar","type": "vehicle",      "lat": 28.64, "lon": 77.32, "violations": 5, "last_check": "2025-09-20"},
        {"id": "BIO001", "name": "Unauthorized Waste Burning Site", "type": "biomass",      "lat": 28.58, "lon": 77.25, "violations": 4, "last_check": "2025-11-28"},
    ]

    def __init__(self):
        logger.info("EnforcementAgent initialized")

    def run(self, city: str) -> list[dict]:
        attribution   = BUS.get(f"attribution_{city}") or {}
        forecast      = BUS.get(f"forecast_{city}") or []
        peak_in_hours = 12

        if forecast:
            fc_df         = pd.DataFrame(forecast)
            peak_idx      = fc_df["aqi_pred"].idxmax() if "aqi_pred" in fc_df else 0
            peak_in_hours = float(fc_df.iloc[peak_idx]["hours_ahead"])

        sources = {s["source"].replace("src_", ""): s["pct"]
                   for s in attribution.get("sources", [])}

        from db.supabase_store import SupabaseStore
        polluter_db = SupabaseStore.get_polluters(city) or self.POLLUTER_DB

        actions = []
        for p in polluter_db:
            src_pct    = sources.get(p["type"], 5.0)
            recidivism = p["violations"] * 15
            urgency    = max(0, 100 - peak_in_hours * 4)
            score      = src_pct * 2 + recidivism + urgency
            actions.append({
                **p,
                "contrib":              round(src_pct, 1),
                "score":                round(score, 1),
                "src_contribution_pct": src_pct,
                "priority_score":       round(score, 1),
                "peak_in_hours":        peak_in_hours,
                "evidence": {
                    "satellite_flag": src_pct > 15,
                    "station_flag":   attribution.get("current_pm25", 0) > 100,
                    "confidence":     attribution.get("overall_confidence", 0.75),
                },
            })

        actions.sort(key=lambda x: x["priority_score"], reverse=True)
        top_actions = actions[:5]

        for action in top_actions:
            action["notice_draft"] = self._draft_notice(action, city)

        BUS.set(f"enforcement_{city}", top_actions)
        logger.info(f"[EnforcementAgent] Top: {top_actions[0]['name']} "
                    f"(score={top_actions[0]['priority_score']})")
        return top_actions

    def _draft_notice(self, action: dict, city: str) -> str:
        if not groq_client:
            return self._mock_notice(action, city)

        prompt = f"""Draft a formal CPCB enforcement notice (under Section 5 of Environment Protection Act 1986) for:

Violator: {action['name']}
Type: {action['type']} emission source
Location: {city} (Lat: {action['lat']}, Lon: {action['lon']})
Prior violations: {action['violations']}
Evidence: Satellite attribution confidence {action['evidence']['confidence']:.0%},
          contributing {action['src_contribution_pct']:.1f}% to current PM2.5 exceedance

Keep it under 150 words. Include: date, reference number, specific CPCB norm violated,
action required within 48 hours, penalty clause reference."""

        try:
            return _groq_chat(system="", user=prompt, max_tokens=300)
        except Exception as e:
            logger.warning(f"Groq API error: {e}")
            return self._mock_notice(action, city)

    @staticmethod
    def _mock_notice(action: dict, city: str) -> str:
        return (
            f"NOTICE REF: CPCB/{city.upper()[:3]}/{datetime.utcnow().strftime('%Y%m%d')}/{action['id']}\n"
            f"Date: {datetime.utcnow().strftime('%d %B %Y')}\n\n"
            f"To: The Owner/Occupier, {action['name']}\n\n"
            f"SUBJECT: Direction under Section 5 of the Environment (Protection) Act, 1986\n\n"
            f"Your premises have been identified as contributing {action['src_contribution_pct']:.1f}% "
            f"of current PM2.5 exceedance in {city} based on satellite-corroborated source attribution. "
            f"This constitutes violation of CPCB ambient air quality standards (PM2.5 > 60 µg/m³). "
            f"You are hereby directed to: (1) Cease operations causing emission immediately, "
            f"(2) Submit compliance report within 48 hours, "
            f"(3) Failure to comply attracts penalty under Section 15 (₹1 lakh/day).\n\n"
            f"CPCB Regional Office, {city}"
        )


# ════════════════════════════════════════════════════════
# AGENT 4 — CITIZEN HEALTH SHIELD AGENT
# ════════════════════════════════════════════════════════
class CitizenHealthShieldAgent:
    LANGUAGES = {
        "en": "English", "hi": "Hindi",    "bn": "Bengali",
        "te": "Telugu",  "mr": "Marathi",  "ta": "Tamil",
        "gu": "Gujarati","kn": "Kannada",  "ml": "Malayalam",
        "pa": "Punjabi", "or": "Odia",     "ur": "Urdu",
    }
    CITY_LANG = {
        "delhi": "hi", "mumbai": "mr", "bengaluru": "kn",
        "kolkata": "bn", "chennai": "ta", "hyderabad": "te",
    }

    def __init__(self):
        if TWILIO_SID and TWILIO_TOKEN:
            from twilio.rest import Client
            self.twilio = Client(TWILIO_SID, TWILIO_TOKEN)
        else:
            self.twilio = None
        logger.info("CitizenHealthShieldAgent initialized")

    def generate_advisory(self, city: str, user_profile: dict = None) -> dict:
        forecast    = BUS.get(f"forecast_{city}") or []
        attribution = BUS.get(f"attribution_{city}") or {}
        profile     = user_profile or {}
        lang        = profile.get("language", self.CITY_LANG.get(city.lower(), "hi"))
        ward        = profile.get("ward", f"{city.title()} Central")
        vulnerable  = profile.get("vulnerable", False)

        next_24h_aqi = 200
        if forecast:
            fc_df = pd.DataFrame(forecast)
            if "aqi_pred" in fc_df:
                next_24h     = fc_df[fc_df["hours_ahead"] <= 24]
                next_24h_aqi = int(next_24h["aqi_pred"].max()) if len(next_24h) else 200

        severity = self._classify_severity(next_24h_aqi)
        dominant = attribution.get("dominant_source", "vehicle exhaust")
        message  = self._compose_message(city, ward, next_24h_aqi, severity,
                                          dominant, lang, vulnerable)

        advisory = {
            "city":          city,
            "ward":          ward,
            "language":      lang,
            "language_name": self.LANGUAGES.get(lang, "English"),
            "aqi_forecast":  next_24h_aqi,
            "severity":      severity,
            "message":       message,
            "timestamp":     datetime.utcnow().isoformat(),
        }
        BUS.set(f"citizen_advisory_{city}", advisory)
        return advisory

    def _classify_severity(self, aqi: int) -> str:
        if aqi <= 50:   return "good"
        if aqi <= 100:  return "satisfactory"
        if aqi <= 200:  return "moderate"
        if aqi <= 300:  return "poor"
        if aqi <= 400:  return "very_poor"
        return "severe"

    def _compose_message(self, city, ward, aqi, severity, dominant,
                          lang, vulnerable) -> str:
        if groq_client:
            return self._groq_message(city, ward, aqi, severity, dominant, lang, vulnerable)
        return self._template_message(city, ward, aqi, severity, lang, vulnerable)

    def _groq_message(self, city, ward, aqi, severity, dominant, lang, vulnerable) -> str:
        lang_name = self.LANGUAGES.get(lang, "Hindi")
        vuln_note = "The user is elderly or has respiratory issues." if vulnerable else ""
        try:
            return _groq_chat(
                system = "You are a helpful multilingual air quality assistant for Indian citizens.",
                user   = f"""Write a WhatsApp air quality advisory in {lang_name}.

City: {city.title()}, Ward: {ward}
Forecast AQI: {aqi} ({severity.replace('_', ' ').title()})
Main source: {dominant}
{vuln_note}

Rules:
- Max 100 words
- Start with AQI severity emoji
- Give 2-3 specific actionable tips
- Mention main source briefly
- Friendly tone, no panic
- Write ONLY in {lang_name}, not English (except proper nouns)""",
                max_tokens = 200,
            )
        except Exception as e:
            logger.warning(f"Groq advisory error: {e}")
            return self._template_message(city, ward, aqi, severity, lang, vulnerable)

    def _template_message(self, city, ward, aqi, severity, lang, vulnerable) -> str:
        templates = {
            "severe":       f"🔴 SEVERE AIR QUALITY ALERT — {ward}, {city.title()}\n\nAQI: {aqi}. Avoid ALL outdoor activity. Wear N95 mask if going out. Keep windows sealed.",
            "very_poor":    f"🟠 Poor Air Quality Warning — {ward}, {city.title()}\n\nAQI: {aqi}. Reduce outdoor activity. Morning walk not advisable. Wear mask outdoors.",
            "poor":         f"🟡 Air Quality Alert — {ward}, {city.title()}\n\nAQI: {aqi}. Limit outdoor exercise. Children and elderly should stay indoors.",
            "moderate":     f"🟢 Moderate Air Quality — {ward}, {city.title()}\n\nAQI: {aqi}. Sensitive groups should reduce prolonged outdoor activity.",
            "satisfactory": f"✅ Air Quality Satisfactory — {ward}, {city.title()}\n\nAQI: {aqi}. Good for outdoor activities.",
            "good":         f"✅ Good Air Quality — {ward}, {city.title()}\n\nAQI: {aqi}. Air is clean. Great day for outdoor activities!",
        }
        return templates.get(severity, templates["moderate"])

    def send_whatsapp(self, to_number: str, message: str) -> bool:
        if not self.twilio:
            logger.warning("Twilio not configured — printing message instead")
            logger.info(f"\n{'='*50}\nWHATSAPP MESSAGE:\n{message}\n{'='*50}")
            return False
        try:
            msg = self.twilio.messages.create(
                body  = message,
                from_ = TWILIO_WHATSAPP_NO,
                to    = to_number if to_number.startswith("whatsapp:") else f"whatsapp:{to_number}",
            )
            logger.success(f"WhatsApp sent: {msg.sid}")
            return True
        except Exception as e:
            logger.error(f"WhatsApp failed: {e}")
            return False

    def handle_chatbot_query(self, user_message: str, city: str,
                              phone: str = None) -> str:
        forecast_data = BUS.get(f"forecast_{city}") or []
        attribution   = BUS.get(f"attribution_{city}") or {}
        fc_summary    = ""
        if forecast_data:
            fc_df = pd.DataFrame(forecast_data)
            if "aqi_pred" in fc_df:
                fc_summary = fc_df.head(96)[["hours_ahead","aqi_pred","aqi_category"]].to_string(index=False)

        system = f"""You are VAYU, a helpful air quality assistant for Indian citizens.
Current city: {city.title()}
Attribution: {json.dumps(attribution, indent=2)}
48-hour forecast:
{fc_summary}

Answer in the SAME language as the user's message.
Be concise (max 100 words). Give specific, actionable advice.
Include AQI numbers when relevant. Use emojis sparingly."""

        if not groq_client:
            reply = self._simple_chatbot(user_message, city)
        else:
            try:
                reply = _groq_chat(system=system, user=user_message, max_tokens=250)
            except Exception as e:
                logger.warning(f"Groq chatbot error: {e}")
                reply = self._simple_chatbot(user_message, city)

        from db.supabase_store import SupabaseStore
        SupabaseStore.log_chat(city, "user", user_message, phone)
        SupabaseStore.log_chat(city, "assistant", reply, phone)
        if phone:
            self.send_whatsapp(phone, reply)
        return reply

    def _simple_chatbot(self, message: str, city: str) -> str:
        forecast = BUS.get(f"forecast_{city}") or []
        aqi      = 200
        if forecast:
            fc_df = pd.DataFrame(forecast)
            if "aqi_pred" in fc_df:
                aqi = int(fc_df["aqi_pred"].iloc[0])
        return (
            f"🌬️ VAYU Air Quality Update — {city.title()}\n"
            f"Current forecast AQI: {aqi}\n"
            f"{'⚠️ Air quality is poor. Limit outdoor activity.' if aqi > 200 else '✅ Air quality is acceptable.'}\n"
            f"For detailed forecast, visit vayu.gov.in"
        )


# ════════════════════════════════════════════════════════
# AGENT 5 — MULTI-CITY COMPARATIVE AGENT
# ════════════════════════════════════════════════════════
class MultiCityComparativeAgent:
    def __init__(self):
        logger.info("MultiCityComparativeAgent initialized")

    def run(self, cities: list[str] = None) -> dict:
        if cities is None:
            cities = list(CITIES.keys())

        report = {
            "generated_at": datetime.utcnow().isoformat(),
            "cities":       {},
            "rankings":     [],
            "insights":     [],
        }

        for city in cities:
            attr     = BUS.get(f"attribution_{city}") or {}
            fc       = BUS.get(f"forecast_{city}") or []
            enf      = BUS.get(f"enforcement_{city}") or []
            peak_aqi = 200
            if fc:
                fc_df    = pd.DataFrame(fc)
                peak_aqi = int(fc_df["aqi_pred"].max()) if "aqi_pred" in fc_df else 200

            report["cities"][city] = {
                "current_pm25":      attr.get("current_pm25", 80),
                "current_aqi":       attr.get("current_aqi", 180),
                "peak_forecast_aqi": peak_aqi,
                "dominant_source":   attr.get("dominant_source", "Unknown"),
                "confidence":        attr.get("overall_confidence", 0.75),
                "pending_actions":   len(enf),
            }

        ranked = sorted(
            [(c, d["current_aqi"]) for c, d in report["cities"].items()],
            key=lambda x: x[1], reverse=True
        )
        report["rankings"] = [{"rank": i+1, "city": c, "aqi": a}
                               for i, (c, a) in enumerate(ranked)]
        report["insights"] = self._generate_insights(report, cities)

        BUS.set("multi_city_report", report)
        logger.info(f"[MultiCityAgent] Report generated for {len(cities)} cities")
        return report

    def _generate_insights(self, report: dict, cities: list) -> list[str]:
        if not groq_client:
            return [
                "Delhi shows highest PM2.5 primarily from vehicle exhaust — consider odd-even policy.",
                "Biomass burning season elevated 3 cities simultaneously — inter-state coordination needed.",
                "Bengaluru's construction dust spike aligns with new metro line Phase 3 work.",
            ]
        summary = json.dumps(report["cities"], indent=2)
        try:
            text = _groq_chat(
                system = "You are an expert air quality analyst for the Indian government.",
                user   = f"""Based on this multi-city air quality data, provide 3-5 actionable cross-city insights for CPCB administrators. Be specific and data-driven. Format as a JSON list of strings only — no preamble, no markdown.

{summary}""",
                max_tokens = 400,
            )
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                return json.loads(match.group())
            return [text[:300]]
        except Exception as e:
            return [f"Cross-city analysis unavailable: {e}"]


# ════════════════════════════════════════════════════════
# ORCHESTRATOR
# ════════════════════════════════════════════════════════
class VAYUOrchestrator:
    def __init__(self):
        self.attribution_agent = SourceAttributionAgent()
        self.forecast_agent    = PredictiveAQIAgent()
        self.enforcement_agent = EnforcementAgent()
        self.citizen_agent     = CitizenHealthShieldAgent()
        self.comparative_agent = MultiCityComparativeAgent()
        logger.info("VAYUOrchestrator ready")

    def run_city(self, city: str, recent_df: pd.DataFrame) -> dict:
        logger.info(f"\n{'═'*50}")
        logger.info(f"VAYU Pipeline — {city.upper()}")
        logger.info(f"{'═'*50}")

        # Auto feature-engineer if raw fetch (8 cols) is passed in
        try:
            from data.preprocess import engineer_features
            if "hour_sin" not in recent_df.columns:
                recent_df = engineer_features(recent_df)
        except Exception as e:
            logger.warning(f"Feature engineering skipped: {e}")

        attr     = self.attribution_agent.run(city, recent_df)
        fc       = self.forecast_agent.run(city, recent_df)
        enf      = self.enforcement_agent.run(city)
        advisory = self.citizen_agent.generate_advisory(city)

        return {
            "city":        city,
            "attribution": attr,
            "forecast":    fc.head(8).to_dict(orient="records"),
            "enforcement": enf[:3],
            "advisory":    advisory,
        }

    def run_all_cities(self, city_data: dict[str, pd.DataFrame]) -> dict:
        results = {}
        for city, df in city_data.items():
            try:
                results[city] = self.run_city(city, df)
            except Exception as e:
                logger.error(f"Pipeline failed for {city}: {e}")
        comparative        = self.comparative_agent.run(list(city_data.keys()))
        results["_comparative"] = comparative
        return results


# ── Quick test
if __name__ == "__main__":
    from data.download_data import generate_live_synthetic
    orchestrator = VAYUOrchestrator()
    test_df      = generate_live_synthetic("delhi")
    result       = orchestrator.run_city("delhi", test_df)

    print("\n── Attribution:")
    for s in result["attribution"]["sources"]:
        print(f"  {s['label']:<25} {s['pct']}%")
    print(f"\n── Enforcement top: {result['enforcement'][0]['name']}")
    print(f"\n── Advisory:\n{result['advisory']['message']}")
