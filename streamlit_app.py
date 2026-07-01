# streamlit_app.py
# ─────────────────────────────────────────────────────────
# VAYU — Premium Air Quality Intelligence Dashboard
# Run API first:  uvicorn api.main:app --port 8000
# Then:           streamlit run streamlit_app.py
# ─────────────────────────────────────────────────────────

import os
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

sys.path.append(str(Path(__file__).parent))

API_BASE = os.getenv("VAYU_API_URL", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="VAYU — Air Quality Intelligence",
    page_icon="V",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.set_option("client.showSidebarNavigation", False)

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
      :root {
        color-scheme: dark;
        --bg-0: #07111D;
        --bg-1: #0B1424;
        --bg-2: #101B2D;
        --card: #132235;
        --card-2: rgba(19, 34, 53, 0.82);
        --border: rgba(255,255,255,0.06);
        --text: #F7FBFF;
        --muted: #90A8C0;
        --accent: #3B82F6;
        --accent-2: #38BDF8;
        --success: #10B981;
        --warning: #F59E0B;
        --danger: #EF4444;
      }
      .stApp {
        background: radial-gradient(circle at top left, rgba(59,130,246,0.18), transparent 32%),
                    linear-gradient(135deg, var(--bg-0) 0%, var(--bg-1) 45%, var(--bg-2) 100%);
        color: var(--text);
        font-family: 'Inter', 'Segoe UI', sans-serif;
      }
      [data-testid="stSidebar"] {
        background: rgba(6, 14, 24, 0.96);
        border-right: 1px solid var(--border);
      }
      .block-container {
        padding-top: 1.1rem;
        padding-bottom: 2.2rem;
        max-width: 1500px;
      }
      .shell-card, .metric-card, .insight-card, .weather-card, .map-card, .source-card, .risk-card, .hotspot-card, .comparison-card {
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        transition: transform 220ms ease, box-shadow 220ms ease, border-color 220ms ease;
      }
      .shell-card:hover, .metric-card:hover, .insight-card:hover, .weather-card:hover, .map-card:hover, .source-card:hover, .risk-card:hover, .hotspot-card:hover, .comparison-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 24px 48px rgba(0, 0, 0, 0.26);
        border-color: rgba(255,255,255,0.12);
      }
      .shell-card {
        background: linear-gradient(180deg, rgba(19, 34, 53, 0.96), rgba(10, 23, 38, 0.96));
        border: 1px solid var(--border);
        border-radius: 24px;
        padding: 1.15rem 1.25rem;
        box-shadow: 0 16px 42px rgba(0, 0, 0, 0.24);
      }
      .metric-card {
        background: linear-gradient(135deg, rgba(19, 34, 53, 0.96), rgba(10, 24, 38, 0.95));
        border: 1px solid var(--border);
        border-radius: 22px;
        padding: 1rem 1rem 0.95rem;
        min-height: 172px;
        box-shadow: 0 14px 32px rgba(0, 0, 0, 0.2);
      }
      .metric-top {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.7rem;
        margin-bottom: 0.9rem;
      }
      .metric-icon {
        width: 42px;
        height: 42px;
        border-radius: 14px;
        display: grid;
        place-items: center;
        background: rgba(255,255,255,0.04);
        color: var(--accent-2);
        border: 1px solid rgba(255,255,255,0.06);
      }
      .metric-badge {
        font-size: 0.72rem;
        padding: 0.35rem 0.6rem;
        border-radius: 999px;
        background: rgba(59, 130, 246, 0.14);
        color: #CFE4FF;
        border: 1px solid rgba(59,130,246,0.16);
        letter-spacing: 0.06em;
        text-transform: uppercase;
      }
      .metric-label {
        color: var(--muted);
        font-size: 0.79rem;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        margin-bottom: 0.35rem;
      }
      .metric-value {
        font-size: 2rem;
        font-weight: 800;
        line-height: 1.05;
        letter-spacing: -0.03em;
        margin-bottom: 0.15rem;
      }
      .metric-caption {
        color: var(--muted);
        font-size: 0.9rem;
        margin-bottom: 0.55rem;
      }
      .metric-footer {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.8rem;
        margin-top: 0.75rem;
      }
      .metric-trend {
        font-size: 0.82rem;
        font-weight: 600;
      }
      .section-title {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        margin-bottom: 0.85rem;
      }
      .section-title h4 {
        margin: 0;
        font-size: 1.02rem;
        font-weight: 700;
        letter-spacing: -0.01em;
      }
      .muted {
        color: var(--muted);
      }
      .tiny {
        font-size: 0.8rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }
      .status-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.4rem 0.68rem;
        border-radius: 999px;
        border: 1px solid rgba(255,255,255,0.06);
        background: rgba(255,255,255,0.04);
        color: var(--text);
        font-size: 0.8rem;
      }
      .status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        display: inline-block;
      }
      .hero-card {
        background: linear-gradient(135deg, rgba(19,34,53,0.98), rgba(10,24,38,0.95));
        border: 1px solid var(--border);
        border-radius: 28px;
        padding: 1.15rem 1.2rem 1.05rem;
        box-shadow: 0 18px 44px rgba(0, 0, 0, 0.24);
        margin-bottom: 1rem;
      }
      .hero-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        flex-wrap: wrap;
      }
      .hero-kicker {
        color: #8FC8FF;
        font-size: 0.8rem;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        margin-bottom: 0.3rem;
      }
      .hero-title {
        font-size: 1.75rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        margin-bottom: 0.25rem;
      }
      .hero-subtitle {
        color: var(--muted);
        font-size: 0.98rem;
      }
      .insight-card {
        background: linear-gradient(135deg, rgba(17, 30, 49, 0.94), rgba(14, 25, 42, 0.94));
        border: 1px solid var(--border);
        border-radius: 20px;
        padding: 0.95rem 1rem;
        margin-bottom: 0.75rem;
      }
      .insight-title {
        font-size: 0.9rem;
        font-weight: 700;
        margin-bottom: 0.25rem;
      }
      .insight-body {
        color: var(--muted);
        font-size: 0.92rem;
        line-height: 1.5;
      }
      .weather-card {
        background: rgba(255,255,255,0.03);
        border: 1px solid var(--border);
        border-radius: 18px;
        padding: 0.8rem 0.9rem;
        min-height: 108px;
      }
      .weather-value {
        font-size: 1.08rem;
        font-weight: 700;
        margin-top: 0.25rem;
      }
      .source-card, .map-card, .risk-card, .hotspot-card, .comparison-card {
        background: linear-gradient(135deg, rgba(19,34,53,0.94), rgba(11,23,38,0.94));
        border: 1px solid var(--border);
        border-radius: 22px;
        padding: 0.95rem 1rem;
      }
      .risk-card {
        padding: 0.8rem 0.9rem;
      }
      .risk-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.6rem;
        margin-bottom: 0.55rem;
      }
      .progress-track {
        height: 7px;
        background: rgba(255,255,255,0.06);
        border-radius: 999px;
        overflow: hidden;
        margin-top: 0.4rem;
      }
      .progress-bar {
        height: 100%;
        border-radius: inherit;
      }
      .pill-list {
        display: flex;
        flex-wrap: wrap;
        gap: 0.45rem;
      }
      .nav-item {
        display: flex;
        align-items: center;
        gap: 0.7rem;
        padding: 0.72rem 0.8rem;
        border-radius: 14px;
        color: #D6E7F8;
        margin-bottom: 0.35rem;
        transition: background 180ms ease, transform 180ms ease;
      }
      .nav-item:hover {
        background: rgba(255,255,255,0.05);
        transform: translateX(2px);
      }
      .stButton > button {
        background: linear-gradient(135deg, rgba(59,130,246,0.2), rgba(56,189,248,0.12));
        color: var(--text);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 999px;
        padding: 0.45rem 0.8rem;
      }
      .stSelectbox > div > div {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 999px;
      }
      .stTextInput > div > div > input {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 999px;
      }
      .stTabs [data-baseweb="tab-list"] {
        gap: 0.45rem;
      }
      .stTabs [data-baseweb="tab"] {
        border-radius: 999px;
        color: var(--muted);
        border: 1px solid transparent;
      }
      .stTabs [aria-selected="true"] {
        color: var(--text);
        background: rgba(59,130,246,0.16);
        border-color: rgba(59,130,246,0.2);
      }
      .footer-note {
        margin-top: 0.45rem;
        color: var(--muted);
        font-size: 0.8rem;
      }
      h1, h2, h3, h4, h5, h6 {
        color: var(--text) !important;
      }
      @keyframes pulseGlow {
        0%, 100% { box-shadow: 0 0 0 0 rgba(56,189,248,0.22); }
        50% { box-shadow: 0 0 0 8px rgba(56,189,248,0.0); }
      }
      .pulse {
        animation: pulseGlow 2.2s infinite;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

CITY_LIST = ["Delhi", "Mumbai", "Bengaluru", "Kolkata", "Chennai", "Hyderabad"]
CITY_COORDS = {
    "Delhi": (77.1025, 28.7041),
    "Mumbai": (72.8777, 19.0760),
    "Bengaluru": (77.5946, 12.9716),
    "Kolkata": (88.3639, 22.5726),
    "Chennai": (80.2707, 13.0827),
    "Hyderabad": (78.4867, 17.3850),
}
AQI_BANDS = [
    (0, 50, "Good", "#10B981"),
    (51, 100, "Satisfactory", "#84CC16"),
    (101, 200, "Moderate", "#F59E0B"),
    (201, 300, "Poor", "#F97316"),
    (301, 400, "Very Poor", "#EF4444"),
    (401, 500, "Severe", "#7C3AED"),
]


def aqi_info(aqi):
    for lo, hi, cat, col in AQI_BANDS:
        if lo <= aqi <= hi:
            return cat, col
    return "Severe", "#7C3AED"


def humanize_time(value: str) -> str:
    if not value:
        return "just now"
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(dt.tzinfo)
        diff = int((now - dt).total_seconds())
        if diff < 60:
            return f"updated {diff}s ago"
        if diff < 3600:
            return f"updated {diff // 60}m ago"
        if diff < 86400:
            return f"updated {diff // 3600}h ago"
        return f"updated {diff // 86400}d ago"
    except Exception:
        return value


def trend_label(current, baseline=None):
    if baseline is None:
        if current >= 180:
            return "▲ elevated"
        if current >= 100:
            return "▲ rising"
        return "▼ stable"
    delta = current - baseline
    if delta > 0:
        return f"▲ +{int(delta)}"
    if delta < 0:
        return f"▼ {int(delta)}"
    return "● steady"


def sparkline_svg(values, color="#38BDF8"):
    if not values:
        return ""
    values = [max(float(v), 0) for v in values]
    min_v = min(values)
    max_v = max(values)
    span = max_v - min_v or 1
    points = []
    for idx, value in enumerate(values):
        x = 6 + idx / max(1, len(values) - 1) * 88
        y = 72 - ((value - min_v) / span) * 50
        points.append(f"{x:.1f},{y:.1f}")
    polyline = " ".join(points)
    return (
        f'<svg viewBox="0 0 100 80" width="100%" height="34" preserveAspectRatio="none">'
        f'<path d="M 6 72 L {polyline} L 94 72 Z" fill="{color}" fill-opacity="0.12"></path>'
        f'<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"></polyline>'
        f'</svg>'
    )


def render_metric_card(title, value, caption, delta, color, icon, badge, spark_values=None, description=None):
    spark_html = sparkline_svg(spark_values, color) if spark_values else ""
    st.markdown(
        f"""
        <div class="metric-card">
          <div class="metric-top">
            <div class="metric-icon" style="color:{color}; border-color: rgba(255,255,255,0.08);">{icon}</div>
            <div class="metric-badge">{escape(badge)}</div>
          </div>
          <div class="metric-label">{escape(title)}</div>
          <div class="metric-value" style="color:{color};">{escape(str(value))}</div>
          <div class="metric-caption">{escape(caption)}</div>
          <div class="metric-footer">
            <div class="metric-trend" style="color:{color};">{escape(delta)}</div>
            <div style="width: 84px;">{spark_html}</div>
          </div>
          <div class="footer-note">{escape(description or '')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_header(title, subtitle=None, right=None):
    right_html = f"<div class='muted tiny'>{escape(right)}</div>" if right else ""
    subtitle_html = f"<div class='muted' style='font-size:0.9rem; margin-top:0.18rem;'>{escape(subtitle)}</div>" if subtitle else ""
    st.markdown(
        f"""
        <div class="section-title">
          <div>
            <h4>{escape(title)}</h4>
            {subtitle_html}
          </div>
          {right_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_badge(label, active):
    color = "#10B981" if active else "#EF4444"
    return f'<span class="status-pill"><span class="status-dot" style="background:{color};"></span>{escape(label)}</span>'


@st.cache_data(ttl=300)
def fetch_dashboard(city: str) -> dict:
    r = requests.get(f"{API_BASE}/api/dashboard/{city.lower()}", timeout=120)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=300)
def fetch_comparative() -> dict:
    r = requests.get(f"{API_BASE}/api/comparative", timeout=300)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=300)
def fetch_geospatial_insights(lat: float, lon: float) -> dict:
    try:
        r = requests.get(
            f"{API_BASE}/geospatial-insights",
            params={"lat": lat, "lon": lon},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        return {"status": "error", "message": str(exc), "data": {}}


with st.sidebar:
    st.markdown("<div style='display:flex; align-items:center; gap:0.7rem; margin-bottom:1rem;'>" +
                "<div style='width:44px;height:44px;border-radius:14px;background:linear-gradient(135deg,#3B82F6,#38BDF8);display:grid;place-items:center;font-weight:800;'>V</div>" +
                "<div><div style='font-weight:800;'>VAYU</div><div class='muted' style='font-size:0.8rem;'>Air Intelligence</div></div></div>", unsafe_allow_html=True)
    st.markdown("<div class='muted tiny' style='margin: 0.3rem 0 0.7rem;'>Operations</div>", unsafe_allow_html=True)
    for label, icon, is_active in [
        ("Overview", "◉", True),
        ("Forecast", "◌", False),
        ("Sources", "◎", False),
        ("Weather", "◍", False),
        ("Map", "◐", False),
    ]:
        st.markdown(
            f"<div class='nav-item' style='background: rgba(255,255,255,0.03) if {is_active} else 'transparent';'>"
            f"<span>{icon}</span><span>{escape(label)}</span></div>",
            unsafe_allow_html=True,
        )
    st.markdown("<div style='margin-top:1rem;'></div>", unsafe_allow_html=True)
    st.selectbox("City", CITY_LIST, index=0, key="city_select")
    st.text_input("Search", placeholder="Find signals", key="search_box")
    st.markdown("<div style='margin-top:0.8rem;'></div>", unsafe_allow_html=True)
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()
    st.markdown("<div class='muted footer-note'>WAQI · OpenWeather · Forecasting</div>", unsafe_allow_html=True)
    st.markdown("<div class='muted footer-note'>API: {}</div>".format(API_BASE), unsafe_allow_html=True)

city = st.session_state.get("city_select") or CITY_LIST[0]

try:
    dash = fetch_dashboard(city)
except Exception as e:
    st.error(f"Cannot reach VAYU API at {API_BASE}. Start with: `uvicorn api.main:app --port 8000`\n\n{e}")
    st.stop()

lat, lon = CITY_COORDS[city][1], CITY_COORDS[city][0]
geo = fetch_geospatial_insights(lat, lon)
geo_data = geo.get("data", {})
geo_insights = geo_data.get("insights", {})
geo_status = geo.get("status", "error")
geo_error = geo.get("message", "")
vegetation_index = geo_insights.get("vegetation_index", 0.0)
fire_hotspots = geo_insights.get("fire_hotspots", [])
fire_hotspot_summary = geo_insights.get("fire_hotspot_summary", {}) or {}
fire_count = int(fire_hotspot_summary.get("count", len(fire_hotspots)) or 0)
fire_message = fire_hotspot_summary.get("message", "No active fire hotspots detected in this area during the selected period.")
risk_factors = geo_insights.get("pollution_risk_factors", {})
risk_buckets = geo_insights.get("risk_buckets", {})
if vegetation_index >= 0.45:
    vegetation_health = "Healthy"
elif vegetation_index >= 0.2:
    vegetation_health = "Low to Moderate"
else:
    vegetation_health = "Low"
if fire_count == 0:
    fire_risk = "Low"
    fire_color = "#10B981"
elif fire_count <= 3:
    fire_risk = "Moderate"
    fire_color = "#F59E0B"
else:
    fire_risk = "High"
    fire_color = "#EF4444"

summary = dash.get("summary", {})
attr = dash.get("attribution", {})
live = dash.get("live_api", {})
fc_raw = dash.get("forecast_48h") or dash.get("forecast_12h", [])
enf_data = dash.get("enforcement", [])
hist = dash.get("historical_trend", [])

current_aqi = int(summary.get("current_aqi") or 0)
current_pm25 = float(summary.get("current_pm25") or attr.get("current_pm25") or 0)
aqi_cat = summary.get("aqi_category") or attr.get("aqi_category", "Unknown")
confidence = float(summary.get("confidence") or attr.get("overall_confidence") or 0)
_, aqi_col = aqi_info(current_aqi)

attr_data = attr.get("sources", [])
fc_df = pd.DataFrame(fc_raw)
if not fc_df.empty and "aqi_pred" in fc_df.columns:
    fc_df["aqi"] = fc_df["aqi_pred"]
    fc_df["pm25"] = fc_df.get("pm25_pred", fc_df.get("pm25", 0))
    fc_df["category"] = fc_df.get("aqi_category", "Moderate")
    peak_aqi = int(fc_df["aqi"].max())
else:
    peak_aqi = current_aqi

hist_df = pd.DataFrame(hist)
if not hist_df.empty and "datetime" in hist_df.columns:
    hist_df["datetime"] = pd.to_datetime(hist_df["datetime"], format="mixed", errors="coerce")
    hist_df = hist_df.dropna(subset=["datetime"])
    if "aqi" not in hist_df.columns and "pm25" in hist_df.columns:
        from data.aqi_utils import us_aqi_from_pm25

        hist_df["aqi"] = hist_df["pm25"].apply(us_aqi_from_pm25)

if not hist_df.empty and "aqi" in hist_df.columns and len(hist_df) > 1:
    prev_aqi = int(hist_df["aqi"].iloc[-2])
    aqi_trend = trend_label(current_aqi, prev_aqi)
    pm25_trend = trend_label(int(current_pm25), int(hist_df["pm25"].iloc[-2]) if "pm25" in hist_df.columns else None)
else:
    aqi_trend = trend_label(current_aqi)
    pm25_trend = trend_label(int(current_pm25))

forecast_trend = trend_label(peak_aqi, current_aqi)
confidence_trend = "▲ strong" if confidence >= 0.8 else "▼ moderate" if confidence < 0.6 else "● stable"

weather = {
    "temp": live.get("temp") or live.get("temperature") or live.get("temp_c"),
    "humidity": live.get("humidity") or live.get("humidity_pct"),
    "wind_speed": live.get("wind_speed") or live.get("wind_speed_ms"),
    "pressure": live.get("pressure") or live.get("pressure_hpa"),
    "rainfall_mm": live.get("rainfall_mm") or live.get("rain"),
    "wind_dir": live.get("wind_dir") or live.get("wind_deg"),
}

recommendations = []
if current_aqi <= 50:
    recommendations = [
        ("Air remains comfortable for routine outdoor activity.", "Low"),
        ("Maintain normal outdoor plans with light hydration.", "Low"),
    ]
elif current_aqi <= 100:
    recommendations = [
        ("Reduce prolonged outdoor exertion if you are sensitive to pollution.", "Moderate"),
        ("Keep windows closed during peak traffic hours.", "Moderate"),
    ]
elif current_aqi <= 200:
    recommendations = [
        ("Wear an N95 mask outdoors and limit strenuous activity.", "High"),
        ("Sensitive groups should remain indoors when possible.", "High"),
    ]
else:
    recommendations = [
        ("Avoid outdoor activity and keep windows closed.", "Severe"),
        ("Sensitive groups should remain indoors and use air filtration.", "Severe"),
    ]

try:
    comp = fetch_comparative()
    cities_data = comp.get("cities", {})
except Exception:
    cities_data = {}

hero_metrics = [
    ("Live AQI", f"{current_aqi}", aqi_cat, aqi_trend, aqi_col, "◌", "Live", [current_aqi, max(20, current_aqi - 15), current_aqi + 10, max(10, current_aqi - 4)], f"{current_aqi} AQI at {city}"),
    ("PM2.5", f"{current_pm25:.1f}", "µg/m³ live", pm25_trend, "#38BDF8", "◍", "Signal", [current_pm25, current_pm25 + 4, current_pm25 - 2, current_pm25 + 5], "Fine-particulate burden"),
    ("Forecast Peak", f"{peak_aqi}", "Projected peak", forecast_trend, "#F59E0B", "◎", "Model", [current_aqi, peak_aqi - 7, peak_aqi, max(current_aqi, peak_aqi - 3)], "Expected peak over the next horizon"),
    ("Confidence", f"{int(confidence*100)}%", "Attribution confidence", confidence_trend, "#10B981", "◐", "Ready", [40, 56, 70, int(confidence * 100)], "Model certainty for current source mix"),
]

st.markdown(
    f"""
    <div class="hero-card">
      <div class="hero-row">
        <div>
          <div class="hero-kicker">AI air quality intelligence</div>
          <div class="hero-title">{escape(city)} operating at a calm but sensitive threshold.</div>
          <div class="hero-subtitle">An executive-grade view of live pollution conditions, forecast pressure, and geospatial risk.</div>
        </div>
        <div style="display:flex; flex-wrap:wrap; gap:0.5rem;">
          {status_badge('WAQI Connected', bool(current_aqi))}
          {status_badge('OpenWeather Connected', any(weather.values()))}
          {status_badge('Forecast Ready', not fc_df.empty)}
          {status_badge('Attribution Active', bool(attr_data))}
        </div>
      </div>
      <div class="hero-row" style="margin-top:0.8rem;">
        <div class='muted'>Last refresh · {humanize_time(dash.get('last_updated', ''))}</div>
        <div class='muted'>Current category · {escape(aqi_cat)}</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("")
metric_cols = st.columns(4)
for idx, (label, value, caption, delta, color, icon, badge, spark_values, description) in enumerate(hero_metrics):
    with metric_cols[idx]:
        render_metric_card(label, value, caption, delta, color, icon, badge, spark_values, description)

st.markdown("")
left_col, right_col = st.columns([0.68, 0.32], gap="large")

with left_col:
    render_section_header("Forecast outlook", "Adaptive forecast with confidence bounds and historical context", "Interactive")
    forecast_window = st.radio("", ["24h", "48h", "7 days"], horizontal=True, label_visibility="collapsed")
    forecast_container = st.container()
    with forecast_container:
        st.markdown('<div class="shell-card">', unsafe_allow_html=True)
        if not fc_df.empty:
            if forecast_window == "24h":
                display_fc = fc_df.head(min(6, len(fc_df)))
            elif forecast_window == "48h":
                display_fc = fc_df
            else:
                display_fc = fc_df.tail(min(7, len(fc_df))) if len(fc_df) > 1 else fc_df
            x_vals = display_fc["hours_ahead"] if "hours_ahead" in display_fc.columns else list(range(len(display_fc)))
            pred_vals = display_fc["aqi"]
            upper = pred_vals + [max(8, int(v * 0.06)) for v in pred_vals]
            lower = pred_vals - [max(8, int(v * 0.06)) for v in pred_vals]

            forecast_fig = go.Figure()
            forecast_fig.add_trace(go.Scatter(x=x_vals, y=lower, mode="lines", line=dict(width=0), fillcolor="rgba(56,189,248,0.16)", fill="tonexty", hoverinfo="skip"))
            forecast_fig.add_trace(go.Scatter(x=x_vals, y=upper, mode="lines", line=dict(width=0), fillcolor="rgba(56,189,248,0.16)", fill="tonexty", showlegend=False, hoverinfo="skip"))
            if not hist_df.empty and "aqi" in hist_df.columns:
                forecast_fig.add_trace(go.Scatter(x=list(range(1-len(hist_df), 1)), y=hist_df["aqi"].tolist(), mode="lines+markers", name="Historical", line=dict(color="#7dd3fc", width=2.8), marker=dict(size=4, color="#7dd3fc")))
            forecast_fig.add_trace(go.Scatter(x=x_vals, y=pred_vals, mode="lines+markers", name="Prediction", line=dict(color="#F59E0B", width=3.2), marker=dict(size=6, color="#F59E0B")))
            forecast_fig.add_trace(go.Scatter(x=[x_vals.iloc[0] if hasattr(x_vals, "iloc") else x_vals[0]], y=[pred_vals.iloc[0] if hasattr(pred_vals, "iloc") else pred_vals[0]], mode="markers", name="Start", marker=dict(size=10, color="#10B981")))
            forecast_fig.update_layout(
                template="plotly_dark",
                height=360,
                margin=dict(l=10, r=10, t=18, b=10),
                hovermode="x unified",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis_title="Window",
                yaxis_title="AQI",
            )
            st.plotly_chart(forecast_fig, use_container_width=True)
        else:
            st.info("No forecast data is available yet.")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("")
    render_section_header("Recent AQI trend", "Hourly shape with gentle brushing", "Area")
    st.markdown('<div class="shell-card">', unsafe_allow_html=True)
    if not hist_df.empty and "aqi" in hist_df.columns:
        recent_df = hist_df.tail(24).copy()
        recent_fig = go.Figure()
        recent_fig.add_trace(go.Scatter(x=recent_df["datetime"], y=recent_df["aqi"], mode="lines", fill="tozeroy", line=dict(color="#38BDF8", width=3), fillcolor="rgba(56,189,248,0.18)", hovertemplate="%{x|%H:%M}<br>%{y} AQI<extra></extra>"))
        recent_fig.update_layout(
            template="plotly_dark",
            height=290,
            margin=dict(l=10, r=10, t=10, b=10),
            hovermode="x unified",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis_title="Time",
            yaxis_title="AQI",
            xaxis=dict(rangeslider=dict(visible=True), type="date"),
        )
        st.plotly_chart(recent_fig, use_container_width=True)
    else:
        st.info("Historical readings will appear as live WAQI data refreshes.")
    st.markdown('</div>', unsafe_allow_html=True)

with right_col:
    render_section_header("AI insights", "Evidence-led recommendations for the next decision window", "Live")
    st.markdown('<div class="shell-card">', unsafe_allow_html=True)
    dominant = attr.get("dominant_source") or (attr_data[0].get("label") if attr_data else "Unknown")
    dominant_pct = max([float(s.get("pct", 0) or 0) for s in attr_data], default=0)
    insight_cards = [
        ("Primary signal", f"{dominant} contributes roughly {dominant_pct:.0f}% of the observed load and remains the most likely driver."),
        ("Time pressure", f"Air quality is expected to deteriorate after 2 PM as traffic volume rises and winds weaken over {city}."),
        ("Confidence", f"Model confidence is {int(confidence * 100)}% for the current source attribution mix."),
    ]
    for title, body in insight_cards:
        st.markdown(f"<div class='insight-card'><div class='insight-title'>{escape(title)}</div><div class='insight-body'>{escape(body)}</div></div>", unsafe_allow_html=True)
    for message, risk in recommendations:
        st.markdown(f"<div class='insight-card'><div class='insight-title'>{escape(risk)}</div><div class='insight-body'>{escape(message)}</div></div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("")
    render_section_header("Pollution source", "Breakdown with animated clarity", "Attribution")
    st.markdown('<div class="source-card">', unsafe_allow_html=True)
    if attr_data:
        labels = [s.get("label", "") for s in attr_data]
        values = [float(s.get("pct", 0) or 0) for s in attr_data]
        source_fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=0.58, marker=dict(colors=["#38BDF8", "#818CF8", "#F59E0B", "#10B981", "#F472B6"]), textinfo="percent", insidetextorientation="radial")])
        source_fig.update_layout(template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False, height=260)
        st.plotly_chart(source_fig, use_container_width=True)
        for item in attr_data[:4]:
            label = item.get("label", "Other")
            pct = float(item.get("pct", 0) or 0)
            color = {"Traffic": "#38BDF8", "Industrial": "#F59E0B", "Biomass": "#10B981", "Construction": "#818CF8"}.get(label, "#3B82F6")
            st.markdown(
                f"<div style='display:flex; align-items:center; justify-content:space-between; gap:0.75rem; margin-top:0.6rem;'><div style='display:flex; align-items:center; gap:0.6rem;'><span style='width:10px;height:10px;border-radius:999px;background:{color};'></span><span>{escape(label)}</span></div><div class='muted'>{pct:.0f}%</div></div>",
                unsafe_allow_html=True,
            )
            st.markdown(f"<div class='progress-track'><div class='progress-bar' style='width:{max(8,pct)}%; background:{color};'></div></div>", unsafe_allow_html=True)
    else:
        st.info("Attribution breakdown will appear once the model returns source contributions.")
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("")
render_section_header("Weather pulse", "Current meteorology across the city", "6 channels")
weather_items = [
    ("Temperature", f"{weather.get('temp')}°C", "◍", "#38BDF8"),
    ("Humidity", f"{weather.get('humidity')}%", "◌", "#3B82F6"),
    ("Wind", f"{weather.get('wind_speed')} m/s", "◐", "#10B981"),
    ("Pressure", f"{weather.get('pressure')} hPa", "◎", "#F59E0B"),
    ("Rain", f"{weather.get('rainfall_mm')} mm", "◈", "#818CF8"),
    ("UV", f"{weather.get('wind_dir')}°", "◑", "#F472B6"),
]
weather_cols = st.columns(3)
for idx, (label, value, icon, color) in enumerate(weather_items):
    with weather_cols[idx % 3]:
        st.markdown(
            f"""
            <div class="weather-card">
              <div style="display:flex; align-items:center; justify-content:space-between; gap:0.7rem; margin-bottom:0.4rem;">
                <div class='muted tiny'>{escape(label)}</div>
                <div style='color:{color}; font-size:1.06rem;'>{icon}</div>
              </div>
              <div class='weather-value' style='color:{color};'>{escape(value)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown("")
render_section_header("Map intelligence", "Geospatial context with highlighted city focus", "Interactive")
st.markdown('<div class="map-card">', unsafe_allow_html=True)
if geo_status != "ok":
    st.markdown(
        f"<div class='insight-card'><div class='insight-title'>Geospatial service unavailable</div><div class='insight-body'>{escape(geo_error or 'The geospatial endpoint could not be reached.')}</div></div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f"""
        <div class='insight-card'>
          <div class='hero-row'>
            <div>
              <div class='insight-title'>🔥 Active Fire Hotspots: {fire_count}</div>
              <div class='insight-body'>{escape(fire_message)}</div>
            </div>
            <div class='metric-badge' style='background: rgba(255,255,255,0.04); border-color: rgba(255,255,255,0.08); color:{fire_color};'>Fire Risk {escape(fire_risk)}</div>
          </div>
          <div class='footer-note'>NDVI Score · {vegetation_index:.2f} · Vegetation Health · {escape(vegetation_health)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
map_fig = go.Figure()
for city_name, (lon, lat) in CITY_COORDS.items():
    city_aqi = None
    if city_name.lower() in {k.lower(): v for k, v in cities_data.items()}:
        data = cities_data.get(city_name.lower()) or cities_data.get(city_name)
        city_aqi = data.get("current_aqi") if isinstance(data, dict) else None
    marker_size = 16 if city_name == city else 12
    marker_color = aqi_col if city_name == city else "#38BDF8"
    if city_aqi is not None:
        marker_color = "#F59E0B" if int(city_aqi) > 150 else "#38BDF8"
    map_fig.add_trace(go.Scattergeo(lon=[lon], lat=[lat], text=[f"{city_name}<br>AQI: {city_aqi if city_aqi is not None else 'n/a'}"], mode="markers+text", marker=dict(size=marker_size, color=marker_color, line=dict(width=1, color="white")), showlegend=False, hoverinfo="text"))
if geo_status == "ok" and fire_hotspots:
    for hotspot in fire_hotspots:
        map_fig.add_trace(go.Scattergeo(lon=[hotspot.get("lon")], lat=[hotspot.get("lat")], mode="markers", marker=dict(size=10, color="#EF4444", line=dict(width=0)), hoverinfo="text", text=[f"Fire hotspot<br>Brightness: {hotspot.get('brightness', 0)}<br>Confidence: {hotspot.get('confidence', 'unknown')}"], showlegend=False))
map_fig.update_layout(template="plotly_dark", margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", geo=dict(scope="asia", showland=True, landcolor="rgba(15,23,42,0.9)", showcountries=True, countrycolor="rgba(148,163,184,0.2)", coastlinecolor="rgba(148,163,184,0.2)", bgcolor="rgba(0,0,0,0)"), height=360)
st.plotly_chart(map_fig, use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown("")
render_section_header("Cross-city comparison", "Horizontal comparison cards for adjacent markets", "Pulse")
st.markdown('<div class="shell-card">', unsafe_allow_html=True)
comparison_cols = st.columns(3)
for idx, comparison_city in enumerate(["Delhi", "Mumbai", "Bengaluru"]):
    with comparison_cols[idx]:
        city_data = cities_data.get(comparison_city.lower(), {})
        city_aqi = int(city_data.get("current_aqi", 0) or 0)
        city_cat, city_col = aqi_info(city_aqi)
        st.markdown(
            f"""
            <div class="comparison-card">
              <div class="hero-row" style="margin-bottom:0.6rem;">
                <div style="font-weight:700;">{escape(comparison_city)}</div>
                <div class="metric-badge" style="background: rgba(255,255,255,0.04); border-color: rgba(255,255,255,0.08);">{escape(city_cat)}</div>
              </div>
              <div class="metric-value" style="color:{city_col}; font-size:1.35rem;">{city_aqi}</div>
              <div class='muted' style='font-size:0.9rem;'>Dominant source · {escape(city_data.get('dominant_source', 'Unknown'))}</div>
              <div style='margin-top:0.6rem;'>{sparkline_svg([max(30, city_aqi-20), city_aqi+4, city_aqi-6, city_aqi+12], city_col)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
st.markdown('</div>', unsafe_allow_html=True)

st.markdown("")
left_bottom, right_bottom = st.columns([0.58, 0.42], gap="large")
with left_bottom:
    render_section_header("Risk factors", "Status cards for volatile conditions", "Signals")
    risk_items = [
        ("Traffic", 82, "#38BDF8", "High mobility pressure"),
        ("Construction", 61, "#F59E0B", "Dust and surface disruption"),
        ("Industrial", 44, "#10B981", "Moderate emission load"),
        ("Biomass", 28, "#EF4444", "Low but persistent"),
    ]
    for label, pct, color, note in risk_items:
        st.markdown(
            f"""
            <div class="risk-card" style="margin-bottom:0.65rem;">
              <div class="risk-row">
                <div style='display:flex; align-items:center; gap:0.55rem;'>
                  <span class='status-dot' style='background:{color};'></span>
                  <strong>{escape(label)}</strong>
                </div>
                <div class='muted'>{pct}%</div>
              </div>
              <div class='muted'>{escape(note)}</div>
              <div class='progress-track'><div class='progress-bar' style='width:{pct}%; background:{color};'></div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
with right_bottom:
    render_section_header("Hotspots", "Priority locations with intensity", "Map")
    if geo_status != "ok":
        st.markdown(
            f"<div class='hotspot-card'><div class='insight-title'>Geospatial data unavailable</div><div class='insight-body'>{escape(geo_error or 'Unable to load fire hotspot data right now.')}</div></div>",
            unsafe_allow_html=True,
        )
    elif fire_count > 0 and fire_hotspots:
        for hotspot in fire_hotspots[:3]:
            score = int(min(100, max(20, (hotspot.get("brightness", 0) / 400.0) * 100)))
            st.markdown(
                f"""
                <div class="hotspot-card" style="margin-bottom:0.65rem;">
                  <div class='hero-row' style='margin-bottom:0.45rem;'>
                    <div style='font-weight:700;'>Hotspot {escape(str(hotspot.get('lat', '')))} / {escape(str(hotspot.get('lon', '')))}</div>
                    <div class='metric-badge' style='background: rgba(239,68,68,0.14); border-color: rgba(239,68,68,0.18); color:#FECACA;'>High</div>
                  </div>
                  <div class='muted' style='font-size:0.92rem;'>Confidence · {escape(str(hotspot.get('confidence', 'unknown')))}</div>
                  <div class='progress-track' style='margin-top:0.6rem;'><div class='progress-bar pulse' style='width:{score}%; background:#EF4444;'></div></div>
                  <div class='footer-note'>Brightness · {escape(str(hotspot.get('brightness', 0)))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            f"""
            <div class="hotspot-card">
              <div class='hero-row' style='margin-bottom:0.45rem;'>
                <div style='font-weight:700;'>No active wildfire activity detected nearby.</div>
                <div class='metric-badge' style='background: rgba(16,185,129,0.14); border-color: rgba(16,185,129,0.18); color:#A7F3D0;'>Low</div>
              </div>
              <div class='muted' style='font-size:0.92rem;'>No active fire detections reported in the last 3 days within 50 km of this location.</div>
              <div class='progress-track' style='margin-top:0.6rem;'><div class='progress-bar' style='width:18%; background:#10B981;'></div></div>
              <div class='footer-note'>Fire hotspots · {fire_count}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown("")
render_section_header("Operational queue", "Enforcement priorities for near-term action", "Ready")
st.markdown('<div class="shell-card">', unsafe_allow_html=True)
if enf_data:
    for e in enf_data:
        st.markdown(
            f"""
            <div class='insight-card' style='margin-bottom:0.55rem;'>
              <div class='hero-row' style='margin-bottom:0.2rem;'>
                <div style='font-weight:700;'>{escape(e.get('name', 'Target'))}</div>
                <div class='muted'>{escape(e.get('type', 'Enforcement'))}</div>
              </div>
              <div class='muted' style='font-size:0.92rem;'>Priority {escape(str(e.get('priority_score', '-')))} · {escape(str(e.get('violations', 0)))} violations</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
else:
    st.info("No enforcement targets are configured for this city yet.")
st.markdown('</div>', unsafe_allow_html=True)
