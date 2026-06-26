# streamlit_app.py
# ─────────────────────────────────────────────────────────
# VAYU — Streamlit Dashboard (reads live data from FastAPI)
# Run API first:  uvicorn api.main:app --port 8000
# Then:           streamlit run streamlit_app.py
# ─────────────────────────────────────────────────────────

import sys
import os
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime

API_BASE = os.getenv("VAYU_API_URL", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="VAYU — Air Quality Intelligence",
    page_icon="🌬️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .stApp { background-color: #0A1628; color: #e2f4ff; }
  [data-testid="stSidebar"] { background-color: #0D2137; }
  .metric-card {
    background: #0D2137; border: 1px solid #1e3a5f;
    border-radius: 12px; padding: 16px; text-align: center;
  }
  .metric-val  { font-size: 2.2rem; font-weight: 800; }
  .metric-lbl  { font-size: 0.75rem; color: #94a3b8; margin-top: 4px; }
  h1, h2, h3 { color: #e2f4ff !important; }
</style>
""", unsafe_allow_html=True)

CITY_LIST = ["Delhi", "Mumbai", "Bengaluru", "Kolkata", "Chennai", "Hyderabad"]

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


with st.sidebar:
    st.markdown("## 🌬️ VAYU")
    st.markdown("*Urban Air Quality Intelligence*")
    st.markdown("---")
    city = st.selectbox("Select City", CITY_LIST, index=0)
    tab = st.radio("View", [
        "📊 Overview",
        "🗂 Source Attribution",
        "📈 Forecast",
        "⚖ Enforcement",
        "🌍 Multi-City",
    ])
    st.markdown("---")
    st.markdown("**Data Sources**")
    st.markdown("● WAQI Air Quality API")
    st.markdown("● OpenWeather Weather API")
    st.markdown("● Trained XGBoost + LSTM models")
    st.markdown("---")
    if st.button("🔄 Refresh Now"):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"API: {API_BASE}")

try:
    dash = fetch_dashboard(city)
except Exception as e:
    st.error(f"Cannot reach VAYU API at {API_BASE}. Start with: `uvicorn api.main:app --port 8000`\n\n{e}")
    st.stop()

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
aqi_cat_col, aqi_col = aqi_info(current_aqi)

attr_data = attr.get("sources", [])
fc_df = pd.DataFrame(fc_raw)
if not fc_df.empty and "aqi_pred" in fc_df.columns:
    fc_df["aqi"] = fc_df["aqi_pred"]
    fc_df["pm25"] = fc_df.get("pm25_pred", fc_df.get("pm25", 0))
    fc_df["category"] = fc_df.get("aqi_category", "Moderate")
    peak_aqi = int(fc_df["aqi"].max())
    peak_hour = float(fc_df.loc[fc_df["aqi"].idxmax(), "hours_ahead"])
else:
    peak_aqi = current_aqi
    peak_hour = 0.0

hist_df = pd.DataFrame(hist)
if not hist_df.empty and "datetime" in hist_df.columns:
    hist_df["datetime"] = pd.to_datetime(hist_df["datetime"])
    if "aqi" not in hist_df.columns and "pm25" in hist_df.columns:
        from data.aqi_utils import us_aqi_from_pm25
        hist_df["aqi"] = hist_df["pm25"].apply(us_aqi_from_pm25)

if tab == "📊 Overview":
    st.markdown(f"## {city} — Air Quality Overview")
    ow = live.get("pollution_source", "WAQI")
    st.caption(
        f"{aqi_label} · Pollution: {ow} · Weather: OpenWeather · "
        f"Updated: {dash.get('last_updated', '')}"
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="metric-card"><div class="metric-val" style="color:{aqi_col}">{current_aqi}</div><div class="metric-lbl">Live AQI (WAQI)</div><div style="color:{aqi_col}">{aqi_cat}</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="metric-card"><div class="metric-val">{current_pm25:.1f}</div><div class="metric-lbl">PM2.5 µg/m³ (live)</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="metric-card"><div class="metric-val">{peak_aqi}</div><div class="metric-lbl">Peak Forecast AQI (12h)</div></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="metric-card"><div class="metric-val">{int(confidence * 100)}%</div><div class="metric-lbl">Attribution confidence</div></div>', unsafe_allow_html=True)

    if not hist_df.empty:
        pm25_std = hist_df["pm25"].std() if "pm25" in hist_df.columns else 0
        n_pts = len(hist_df)

        if n_pts >= 2 and pm25_std > 0.01:
            st.markdown("### Recent readings (WAQI — built from live refreshes)")
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=hist_df["datetime"], y=hist_df["pm25"],
                name="PM2.5", mode="lines+markers", line=dict(color="#0D9488"),
            ))
            fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.markdown("### 12-hour forecast (LSTM)")
            st.caption(
                "WAQI returns one live snapshot per refresh — not a 24h history. "
                "The trend chart fills in as you refresh (every ~15 min). "
                "Until then, here is the model forecast."
            )
            fc_12 = fc_df[fc_df["hours_ahead"] <= 12] if "hours_ahead" in fc_df.columns else fc_df.head(48)
            if not fc_12.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=fc_12["hours_ahead"], y=fc_12["aqi"],
                    name="Forecast AQI", line=dict(color="#F59E0B"),
                ))
                fig.update_layout(
                    template="plotly_dark", height=300,
                    xaxis_title="Hours ahead", yaxis_title="Live AQI (WAQI)",
                    margin=dict(l=0, r=0, t=30, b=0),
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Refresh again in a few minutes to start building a historical trend.")

elif tab == "🗂 Source Attribution":
    st.markdown("### Source Attribution (XGBoost)")
    st.caption(f"Confidence: {int(confidence * 100)}% · Method: {attr.get('confidence_method', 'model')}")
    for s in attr_data:
        st.markdown(f"**{s['label']}** — {s['pct']}%")
        st.progress(min(1.0, s["pct"] / 100))

elif tab == "📈 Forecast":
    st.markdown("### 48-Hour Forecast (LSTM)")
    if not fc_df.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=fc_df["hours_ahead"], y=fc_df["aqi"], name="Live AQI (WAQI) forecast", line=dict(color="#F59E0B")))
        fig.update_layout(template="plotly_dark", height=400, xaxis_title="Hours ahead", yaxis_title="Live AQI (WAQI)")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(fc_df[["hours_ahead", "pm25_pred", "aqi_pred", "aqi_category"]].head(48) if "pm25_pred" in fc_df.columns else fc_df.head(48))
    else:
        st.warning("No forecast data yet.")

elif tab == "⚖ Enforcement":
    st.markdown("### Enforcement Queue — " + city)
    if enf_data:
        for e in enf_data:
            st.markdown(f"**{e.get('name')}** ({e.get('type')}) — score {e.get('priority_score')}")
            st.caption(f"Contribution: {e.get('src_contribution_pct')}% · Violations: {e.get('violations')}")
    else:
        st.info("No enforcement targets configured for this city.")

elif tab == "🌍 Multi-City":
    try:
        comp = fetch_comparative()
        cities_data = comp.get("cities", {})
        rows = []
        for c, d in cities_data.items():
            rows.append({
                "City": c.title(),
                "PM2.5": d.get("current_pm25"),
                "Live AQI (WAQI)": d.get("current_aqi"),
                "Confidence": f"{int((d.get('confidence') or 0) * 100)}%",
                "Dominant": d.get("dominant_source"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    except Exception as e:
        st.error(f"Comparative data unavailable: {e}")
