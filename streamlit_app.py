# streamlit_app.py
# ─────────────────────────────────────────────────────────
# VAYU — Streamlit Dashboard (reads live data from FastAPI)
# Run API first:  uvicorn api.main:app --port 8000
# Then:           streamlit run streamlit_app.py
# ─────────────────────────────────────────────────────────

import os
import sys
from datetime import datetime, timezone
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

st.markdown(
    """
    <style>
      :root {
        color-scheme: dark;
      }
      .stApp {
        background: linear-gradient(135deg, #06121f 0%, #081221 35%, #0b1c2e 100%);
        color: #e8f4ff;
      }
      [data-testid="stSidebar"] {
        background: rgba(7, 16, 31, 0.94);
        border-right: 1px solid rgba(93, 155, 255, 0.16);
      }
      .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
      }
      .hero-card, .glass-card, .kpi-card, .status-chip {
        backdrop-filter: blur(14px);
        -webkit-backdrop-filter: blur(14px);
        transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
      }
      .hero-card:hover, .glass-card:hover, .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 16px 36px rgba(0, 0, 0, 0.25);
      }
      .hero-card {
        background: linear-gradient(135deg, rgba(8, 27, 49, 0.92), rgba(12, 38, 67, 0.9));
        border: 1px solid rgba(123, 179, 255, 0.18);
        border-radius: 24px;
        padding: 1.3rem 1.4rem;
        box-shadow: 0 14px 38px rgba(0, 0, 0, 0.22);
      }
      .glass-card {
        background: rgba(8, 18, 33, 0.86);
        border: 1px solid rgba(123, 179, 255, 0.16);
        border-radius: 20px;
        padding: 1rem 1.1rem;
        box-shadow: 0 12px 28px rgba(0, 0, 0, 0.2);
      }
      .kpi-card {
        background: linear-gradient(135deg, rgba(10, 27, 47, 0.95), rgba(13, 38, 67, 0.95));
        border: 1px solid rgba(123, 179, 255, 0.18);
        border-radius: 18px;
        padding: 1rem 1rem 0.9rem;
        min-height: 134px;
        box-shadow: 0 10px 26px rgba(0, 0, 0, 0.2);
      }
      .kpi-value {
        font-size: 2rem;
        font-weight: 700;
        letter-spacing: -0.02em;
      }
      .kpi-subtitle {
        font-size: 0.78rem;
        color: #8fb0ca;
        margin-top: 0.2rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }
      .kpi-trend {
        font-size: 0.84rem;
        margin-top: 0.5rem;
        font-weight: 600;
      }
      .status-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.4rem 0.65rem;
        border-radius: 999px;
        border: 1px solid rgba(123, 179, 255, 0.16);
        background: rgba(8, 24, 41, 0.9);
        font-size: 0.8rem;
        color: #cfe7ff;
      }
      .status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        display: inline-block;
      }
      .section-title {
        font-size: 1.02rem;
        font-weight: 700;
        color: #f4fbff;
        margin-bottom: 0.5rem;
      }
      .subtle {
        color: #87a9c8;
      }
      h1, h2, h3 {
        color: #f5fbff !important;
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


def status_badge(label, active):
    color = "#16a34a" if active else "#ef4444"
    return f'<span class="status-chip"><span class="status-dot" style="background:{color};"></span>{label}</span>'


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
    st.markdown("## VAYU")
    st.markdown("Air Quality Intelligence Platform")
    st.markdown("---")
    city = st.selectbox("City", CITY_LIST, index=0)
    st.markdown("---")
    st.markdown("**Data sources**")
    st.caption("WAQI live AQI")
    st.caption("OpenWeather meteorology")
    st.caption("XGBoost attribution")
    st.caption("LSTM forecasting")
    st.markdown("---")
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"API: {API_BASE}")

try:
    dash = fetch_dashboard(city)
except Exception as e:
    st.error(f"Cannot reach VAYU API at {API_BASE}. Start with: `uvicorn api.main:app --port 8000`\n\n{e}")
    st.stop()

lat, lon = CITY_COORDS[city][1], CITY_COORDS[city][0]
geo = fetch_geospatial_insights(lat, lon)

summary = dash.get("summary", {})
attr = dash.get("attribution", {})
live = dash.get("live_api", {})
fc_raw = dash.get("forecast_48h") or dash.get("forecast_12h", [])
enf_data = dash.get("enforcement", [])
hist = dash.get("historical_trend", [])

current_aqi = int(summary.get("current_aqi") or 0)
current_pm25 = float(summary.get("current_pm25") or attr.get("current_pm25") or 0)
aqi_cat = summary.get("aqi_category") or attr.get("aqi_category", "Unknown")
aqi_label = summary.get("aqi_label", "Live AQI (WAQI)")
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

st.markdown(
    f"""
    <div class="hero-card">
      <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:1rem; flex-wrap:wrap;">
        <div>
          <div style="font-size:0.84rem; letter-spacing:0.2em; text-transform:uppercase; color:#7bb6ff;">AI AIR QUALITY INTELLIGENCE</div>
          <div style="font-size:2.1rem; font-weight:800; margin-top:0.28rem;">VAYU</div>
          <div style="font-size:1.1rem; color:#cfe8ff; margin-top:0.15rem;">Urban air quality monitoring, forecasting, and source attribution</div>
        </div>
        <div style="text-align:right;">
          <div class="subtle" style="font-size:0.8rem; text-transform:uppercase; letter-spacing:0.08em;">Last refresh</div>
          <div style="font-size:1rem; font-weight:700; margin-top:0.2rem;">{humanize_time(dash.get('last_updated', ''))}</div>
        </div>
      </div>
      <div style="margin-top:1rem; display:flex; flex-wrap:wrap; gap:0.55rem;">
        {status_badge('WAQI Connected', bool(current_aqi))}
        {status_badge('OpenWeather Connected', any(weather.values()))}
        {status_badge('Forecast Model Ready', not fc_df.empty)}
        {status_badge('Attribution Ready', bool(attr_data))}
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("")
st.columns(4)

kpi_cols = st.columns(4)
with kpi_cols[0]:
    st.markdown(
        f"""
        <div class="kpi-card">
          <div class="kpi-subtitle">Live AQI</div>
          <div class="kpi-value" style="color:{aqi_col};">{current_aqi}</div>
          <div class="kpi-subtitle">{aqi_cat}</div>
          <div class="kpi-trend" style="color:{aqi_col};">{aqi_trend}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with kpi_cols[1]:
    st.markdown(
        f"""
        <div class="kpi-card">
          <div class="kpi-subtitle">PM2.5</div>
          <div class="kpi-value" style="color:#78c5ff;">{current_pm25:.1f}</div>
          <div class="kpi-subtitle">µg/m³ live</div>
          <div class="kpi-trend" style="color:#78c5ff;">{pm25_trend}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with kpi_cols[2]:
    st.markdown(
        f"""
        <div class="kpi-card">
          <div class="kpi-subtitle">Peak Forecast (12h)</div>
          <div class="kpi-value" style="color:#f59e0b;">{peak_aqi}</div>
          <div class="kpi-subtitle">Projected peak AQI</div>
          <div class="kpi-trend" style="color:#f59e0b;">{forecast_trend}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with kpi_cols[3]:
    st.markdown(
        f"""
        <div class="kpi-card">
          <div class="kpi-subtitle">Forecast Confidence</div>
          <div class="kpi-value" style="color:#34d399;">{int(confidence * 100)}%</div>
          <div class="kpi-subtitle">Attribution confidence</div>
          <div class="kpi-trend" style="color:#34d399;">{confidence_trend}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("")
left_col, right_col = st.columns([0.7, 0.3])

with left_col:
    with st.container():
        st.markdown('<div class="glass-card"><div class="section-title">Forecast outlook</div></div>', unsafe_allow_html=True)
        if not fc_df.empty:
            forecast_fig = go.Figure()
            x_vals = fc_df["hours_ahead"] if "hours_ahead" in fc_df.columns else list(range(len(fc_df)))
            pred_vals = fc_df["aqi"]
            upper = pred_vals + [max(8, int(v * 0.06)) for v in pred_vals]
            lower = pred_vals - [max(8, int(v * 0.06)) for v in pred_vals]

            forecast_fig.add_trace(
                go.Scatter(
                    x=x_vals,
                    y=lower,
                    mode="lines",
                    line=dict(width=0),
                    fillcolor="rgba(56, 189, 248, 0.16)",
                    fill="tonexty",
                    name="Confidence Interval",
                    hoverinfo="skip",
                )
            )
            forecast_fig.add_trace(
                go.Scatter(
                    x=x_vals,
                    y=upper,
                    mode="lines",
                    line=dict(width=0),
                    fillcolor="rgba(56, 189, 248, 0.16)",
                    fill="tonexty",
                    showlegend=False,
                    hoverinfo="skip",
                )
            )
            if not hist_df.empty and "aqi" in hist_df.columns:
                forecast_fig.add_trace(
                    go.Scatter(
                        x=list(range(1 - len(hist_df), 1)),
                        y=hist_df["aqi"].tolist(),
                        mode="lines+markers",
                        name="Historical AQI",
                        line=dict(color="#7dd3fc", width=3),
                        marker=dict(size=5, color="#7dd3fc"),
                    )
                )
            forecast_fig.add_trace(
                go.Scatter(
                    x=x_vals,
                    y=pred_vals,
                    mode="lines+markers",
                    name="Predicted AQI",
                    line=dict(color="#f59e0b", width=3),
                    marker=dict(size=6, color="#f59e0b"),
                )
            )
            forecast_fig.add_trace(
                go.Scatter(
                    x=[x_vals.iloc[0] if hasattr(x_vals, "iloc") else x_vals[0]],
                    y=[pred_vals.iloc[0] if hasattr(pred_vals, "iloc") else pred_vals[0]],
                    mode="markers",
                    name="Prediction Start",
                    marker=dict(size=10, color="#22c55e"),
                )
            )
            forecast_fig.update_layout(
                template="plotly_dark",
                height=360,
                margin=dict(l=10, r=10, t=20, b=10),
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis_title="Hours ahead",
                yaxis_title="AQI",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(forecast_fig, use_container_width=True)
        else:
            st.info("No forecast data is available yet.")

    st.markdown("")
    with st.container():
        st.markdown('<div class="glass-card"><div class="section-title">Recent AQI trend</div></div>', unsafe_allow_html=True)
        if not hist_df.empty and "aqi" in hist_df.columns:
            recent_df = hist_df.tail(24).copy()
            recent_fig = go.Figure()
            recent_fig.add_trace(
                go.Scatter(
                    x=recent_df["datetime"],
                    y=recent_df["aqi"],
                    mode="lines+markers",
                    name="AQI",
                    line=dict(color="#7dd3fc", width=3),
                    marker=dict(size=6, color="#38bdf8"),
                )
            )
            recent_fig.update_layout(
                template="plotly_dark",
                height=290,
                margin=dict(l=10, r=10, t=10, b=10),
                hovermode="x unified",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis_title="Time",
                yaxis_title="AQI",
            )
            st.plotly_chart(recent_fig, use_container_width=True)
        else:
            st.info("Historical readings will appear as live WAQI data refreshes.")

with right_col:
    with st.container():
        st.markdown('<div class="glass-card"><div class="section-title">Pollution source</div></div>', unsafe_allow_html=True)
        if attr_data:
            labels = [s.get("label", "") for s in attr_data]
            values = [float(s.get("pct", 0) or 0) for s in attr_data]
            source_fig = go.Figure(
                data=[go.Pie(labels=labels, values=values, hole=0.55, marker=dict(colors=["#38bdf8", "#818cf8", "#f59e0b", "#34d399", "#f472b6"]), textinfo="percent+label", insidetextorientation="radial")]
            )
            source_fig.update_layout(
                template="plotly_dark",
                margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
                height=260,
            )
            st.plotly_chart(source_fig, use_container_width=True)
            dominant = attr.get("dominant_source") or (attr_data[0].get("label") if attr_data else "Unknown")
            dominant_pct = max([float(s.get("pct", 0) or 0) for s in attr_data], default=0)
            explanation = (
                f"{dominant} contributes approximately {dominant_pct:.0f}% of the observed signal."
                if dominant_pct
                else "The model is still calibrating this attribution profile."
            )
            st.markdown(f"<div class='subtle'><strong>Dominant source</strong><br>{dominant}</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='subtle'><strong>Confidence</strong><br>{int(confidence * 100)}%</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='subtle'><strong>Explanation</strong><br>{explanation}</div>", unsafe_allow_html=True)
        else:
            st.info("Attribution breakdown will appear once the model returns source contributions.")

    st.markdown("")
    with st.container():
        st.markdown('<div class="glass-card"><div class="section-title">Weather summary</div></div>', unsafe_allow_html=True)
        weather_items = [
            ("Temperature", f"{weather.get('temp')}°C"),
            ("Humidity", f"{weather.get('humidity')}%"),
            ("Wind", f"{weather.get('wind_speed')} m/s"),
            ("Pressure", f"{weather.get('pressure')} hPa"),
            ("Rainfall", f"{weather.get('rainfall_mm')} mm"),
            ("Wind Dir", f"{weather.get('wind_dir')}°"),
        ]
        cols = st.columns(2)
        for idx, (label, value) in enumerate(weather_items):
            with cols[idx % 2]:
                st.markdown(
                    f"""
                    <div class="glass-card" style="margin-bottom:0.6rem; padding:0.7rem 0.8rem;">
                      <div class="subtle" style="font-size:0.72rem; text-transform:uppercase; letter-spacing:0.08em;">{label}</div>
                      <div style="font-size:1.05rem; font-weight:700; margin-top:0.18rem;">{value}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    geo_info = geo.get("data", {})
    geo_insights = geo_info.get("insights", {})
    geo_status = geo.get("status", "error")
    geo_error = geo.get("message", "")
    vegetation_index = geo_insights.get("vegetation_index", 0.0)
    fire_hotspots = geo_insights.get("fire_hotspots", [])
    risk_factors = geo_insights.get("pollution_risk_factors", {})
    risk_buckets = geo_insights.get("risk_buckets", {})

    st.markdown(
        '<div class="glass-card"><div class="section-title">Geospatial intelligence</div></div>',
        unsafe_allow_html=True,
    )
    if geo_status == "ok" and geo_insights:
        st.markdown(
            f"""
            <div class="glass-card" style="padding:0.9rem 1rem; margin-bottom:0.65rem;">
              <div style="display:flex; justify-content:space-between; gap:1rem; flex-wrap:wrap;">
                <div>
                  <div class="subtle">Vegetation index</div>
                  <div style="font-size:1.1rem; font-weight:700;">{vegetation_index:.3f}</div>
                </div>
                <div>
                  <div class="subtle">Fire hotspots</div>
                  <div style="font-size:1.1rem; font-weight:700;">{len(fire_hotspots)}</div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        bucket_html = "".join(
            f'<div class="status-chip" style="margin-right:0.4rem; margin-bottom:0.4rem; border-color:rgba(255,255,255,0.1); background:rgba(255,255,255,0.05);">'
            f'<span class="status-dot" style="background:{"#10B981" if color=="green" else "#FBBF24" if color=="yellow" else "#F97316" if color=="orange" else "#EF4444"};"></span>'
            f'{key.title()}: {color}</div>'
            for key, color in risk_buckets.items()
        )
        st.markdown(
            f"""
            <div class=\"glass-card\" style=\"padding:0.85rem 0.95rem; margin-bottom:0.65rem;\">
              <div class=\"subtle\">Risk factors</div>
              <div style=\"display:flex; flex-wrap:wrap; gap:0.4rem; margin-top:0.55rem;\">{bucket_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if fire_hotspots:
            hotspot_summary = "".join(
                f"<li>{h.get('timestamp')} @ {h.get('lat'):.3f},{h.get('lon'):.3f} ({h.get('confidence')})</li>"
                for h in fire_hotspots[:3]
            )
            st.markdown(
                f"""
                <div class="glass-card" style="padding:0.85rem 0.95rem;">
                  <div class="subtle">Top fire hotspots</div>
                  <ul style="margin:0.6rem 0 0 1rem;">{hotspot_summary}</ul>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("Geospatial intelligence is not available for this city or endpoint is disabled.")

st.markdown("")
st.markdown('<div class="glass-card"><div class="section-title">City network</div></div>', unsafe_allow_html=True)
map_fig = go.Figure()
for city_name, (lon, lat) in CITY_COORDS.items():
    city_aqi = None
    if city_name.lower() in {k.lower(): v for k, v in cities_data.items()}:
        data = cities_data.get(city_name.lower()) or cities_data.get(city_name)
        city_aqi = data.get("current_aqi") if isinstance(data, dict) else None
    else:
        city_aqi = None
    marker_size = 16 if city_name == city else 12
    marker_color = aqi_col if city_name == city else "#38bdf8"
    if city_aqi is not None:
        marker_color = "#f59e0b" if int(city_aqi) > 150 else "#38bdf8"
    map_fig.add_trace(
        go.Scattergeo(
            lon=[lon],
            lat=[lat],
            text=[f"{city_name}<br>AQI: {city_aqi if city_aqi is not None else 'n/a'}"],
            mode="markers+text",
            marker=dict(size=marker_size, color=marker_color, line=dict(width=1, color="white")),
            showlegend=False,
            hoverinfo="text",
        )
    )
map_fig.update_layout(
    template="plotly_dark",
    margin=dict(l=8, r=8, t=8, b=8),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    geo=dict(
        scope="asia",
        showland=True,
        landcolor="rgba(15, 23, 42, 0.8)",
        showcountries=True,
        countrycolor="rgba(148, 163, 184, 0.25)",
        coastlinecolor="rgba(148, 163, 184, 0.25)",
        bgcolor="rgba(0,0,0,0)",
    ),
    height=320,
)
st.plotly_chart(map_fig, use_container_width=True)

st.markdown("")
bottom_cols = st.columns([0.65, 0.35])
with bottom_cols[0]:
    st.markdown('<div class="glass-card"><div class="section-title">Operational queue</div></div>', unsafe_allow_html=True)
    if enf_data:
        for e in enf_data:
            st.markdown(
                f"""
                <div class="glass-card" style="margin-bottom:0.55rem; padding:0.75rem 0.8rem;">
                  <div style="display:flex; justify-content:space-between; align-items:center; gap:0.5rem; margin-bottom:0.2rem;">
                    <strong>{e.get('name', 'Target')}</strong>
                    <span style="font-size:0.8rem; color:#7dd3fc;">score {e.get('priority_score', '-')}</span>
                  </div>
                  <div class="subtle">{e.get('type', 'Enforcement')} · {e.get('violations', 0)} violations</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("No enforcement targets are configured for this city yet.")

with bottom_cols[1]:
    st.markdown('<div class="glass-card"><div class="section-title">Cross-city pulse</div></div>', unsafe_allow_html=True)
    if cities_data:
        rows = []
        for c, d in cities_data.items():
            rows.append({
                "City": c.title(),
                "AQI": d.get("current_aqi"),
                "Dominant": d.get("dominant_source"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Comparative city data will appear after the API responds.")
