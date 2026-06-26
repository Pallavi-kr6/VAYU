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

# ── Lazy-load ML models (required — no mock fallback)
def _load_attribution():
    from models.train_attribution import AttributionInference
    return AttributionInference()

def _load_forecast():
    from models.train_forecast import ForecastInference
    return ForecastInference()

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

        result = self.model.predict(recent_df)

        from data.aqi_utils import waqi_aqi_category

        current_pm25 = float(recent_df["pm25"].iloc[-1])
        current_pm10 = float(
            recent_df["pm10"].iloc[-1] if "pm10" in recent_df.columns
            else current_pm25 * 1.8
        )
        if "aqi" in recent_df.columns:
            live_aqi = int(recent_df["aqi"].iloc[-1])
        else:
            from data.aqi_utils import us_aqi_from_pm25
            live_aqi = us_aqi_from_pm25(current_pm25)

        result["city"]              = city
        result["timestamp"]         = datetime.utcnow().isoformat()
        result["current_pm25"]      = current_pm25
        result["current_pm10"]      = current_pm10
        result["current_aqi"]       = live_aqi
        result["aqi_category"]      = waqi_aqi_category(live_aqi)
        result["aqi_source"]        = "waqi"
        result["aqi_label"]         = f"Live AQI (WAQI) {live_aqi}"

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

    @staticmethod
    def _pm25_to_aqi(pm25: float) -> int:
        from data.aqi_utils import us_aqi_from_pm25
        return us_aqi_from_pm25(pm25)


# ════════════════════════════════════════════════════════
# AGENT 2 — PREDICTIVE AQI AGENT
# ════════════════════════════════════════════════════════
class PredictiveAQIAgent:
    def __init__(self):
        self.model = _load_forecast()
        logger.info("PredictiveAQIAgent initialized")

    def run(self, city: str, recent_df: pd.DataFrame, hours: int = 48) -> pd.DataFrame:
        logger.info(f"[ForecastAgent] Generating {hours}h forecast for {city}...")

        forecast = self.model.predict(recent_df, n_steps=hours * 4)

        BUS.set(f"forecast_{city}", forecast.to_dict(orient="records"))
        peak_idx = forecast["aqi_pred"].idxmax()
        peak_row = forecast.iloc[peak_idx]
        logger.info(f"  Peak AQI {peak_row['aqi_pred']:.0f} "
                    f"({peak_row['aqi_category']}) at +{peak_row['hours_ahead']:.1f}h")
        return forecast

    @staticmethod
    def _aqi_to_cat(aqi: int) -> str:
        from data.aqi_utils import aqi_category
        return aqi_category(aqi)


# ════════════════════════════════════════════════════════
# AGENT 3 — ENFORCEMENT INTELLIGENCE AGENT
# ════════════════════════════════════════════════════════
class EnforcementAgent:
    def __init__(self):
        logger.info("EnforcementAgent initialized")

    def run(self, city: str) -> list[dict]:
        from data.enforcement_assets import get_enforcement_assets

        attribution   = BUS.get(f"attribution_{city}") or {}
        forecast      = BUS.get(f"forecast_{city}") or []
        peak_in_hours = 12.0

        if forecast:
            fc_df         = pd.DataFrame(forecast)
            peak_idx      = fc_df["aqi_pred"].idxmax() if "aqi_pred" in fc_df else 0
            peak_in_hours = float(fc_df.iloc[peak_idx]["hours_ahead"])

        sources = {s["source"].replace("src_", ""): s["pct"]
                   for s in attribution.get("sources", [])}

        from db.supabase_store import SupabaseStore
        polluter_db = SupabaseStore.get_polluters(city)
        if not polluter_db:
            polluter_db = get_enforcement_assets(city)

        if not polluter_db:
            logger.warning(f"[EnforcementAgent] No enforcement targets for {city}")
            BUS.set(f"enforcement_{city}", [])
            return []

        attr_confidence = attribution.get("overall_confidence", 0.0)

        actions = []
        for p in polluter_db:
            src_pct    = sources.get(p["type"], 0.0)
            recidivism = p["violations"] * 15
            urgency    = max(0, 100 - peak_in_hours * 4)
            score      = src_pct * 2 + recidivism + urgency
            actions.append({
                **p,
                "city":                 city,
                "contrib":              round(src_pct, 1),
                "score":                round(score, 1),
                "src_contribution_pct": src_pct,
                "priority_score":       round(score, 1),
                "peak_in_hours":        peak_in_hours,
                "evidence": {
                    "satellite_flag": src_pct > 15,
                    "station_flag":   attribution.get("current_pm25", 0) > 100,
                    "confidence":     attr_confidence,
                },
            })

        actions.sort(key=lambda x: x["priority_score"], reverse=True)
        top_actions = actions[:5]

        for action in top_actions:
            action["notice_draft"] = self._draft_notice(action, city)

        BUS.set(f"enforcement_{city}", top_actions)
        if top_actions:
            logger.info(f"[EnforcementAgent] Top ({city}): {top_actions[0]['name']} "
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

        next_24h_aqi = None
        if forecast:
            fc_df = pd.DataFrame(forecast)
            if "aqi_pred" in fc_df:
                next_24h     = fc_df[fc_df["hours_ahead"] <= 24]
                if len(next_24h):
                    next_24h_aqi = int(next_24h["aqi_pred"].max())

        if next_24h_aqi is None:
            next_24h_aqi = int(attribution.get("current_aqi", 0))

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
        attribution = BUS.get(f"attribution_{city}") or {}
        aqi = int(attribution.get("current_aqi", 0))
        if forecast:
            fc_df = pd.DataFrame(forecast)
            if "aqi_pred" in fc_df.columns and len(fc_df):
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
            peak_aqi = 0
            if fc:
                fc_df    = pd.DataFrame(fc)
                peak_aqi = int(fc_df["aqi_pred"].max()) if "aqi_pred" in fc_df else 0

            report["cities"][city] = {
                "current_pm25":      attr.get("current_pm25"),
                "current_aqi":       attr.get("current_aqi"),
                "peak_forecast_aqi": peak_aqi,
                "dominant_source":   attr.get("dominant_source"),
                "confidence":        attr.get("overall_confidence"),
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
            insights = []
            for city, d in report["cities"].items():
                insights.append(
                    f"{city.title()}: Live AQI (WAQI) {d.get('current_aqi')} — "
                    f"dominant source {d.get('dominant_source')} "
                    f"(confidence {int(d.get('confidence', 0) * 100)}%)."
                )
            return insights[:5]
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


# ── Quick test (requires OPENWEATHER_API_KEY in .env)
if __name__ == "__main__":
    from config.settings import OPENWEATHER_API_KEY, WAQI_API_KEY
    from data.download_data import fetch_openweather_live
    from data.preprocess import engineer_features

    orchestrator = VAYUOrchestrator()
    raw_df, _ = fetch_openweather_live(
        "delhi", api_key=OPENWEATHER_API_KEY, waqi_api_key=WAQI_API_KEY,
    )
    feat_df = engineer_features(raw_df)
    result = orchestrator.run_city("delhi", feat_df)

    print("\n── Attribution:")
    for s in result["attribution"]["sources"]:
        print(f"  {s['label']:<25} {s['pct']}%")
    print(f"\n── Enforcement top: {result['enforcement'][0]['name']}")
    print(f"\n── Advisory:\n{result['advisory']['message']}")
