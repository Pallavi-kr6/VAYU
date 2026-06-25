// frontend/src/App.jsx
// ─────────────────────────────────────────────────────────
// VAYU Dashboard — React frontend
// Tabs: Live Map | Attribution | Forecast | Enforcement | Chatbot
// ─────────────────────────────────────────────────────────

import { useState, useEffect, useCallback } from "react";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, RadialBarChart, RadialBar,
} from "recharts";

// ── Config ────────────────────────────────────────────────
const API = "http://localhost:8000/api";

const CITIES = ["delhi", "mumbai", "bengaluru", "kolkata", "chennai", "hyderabad"];

const AQI_COLORS = {
  Good:         { bg: "#10B981", text: "#fff", ring: "#059669" },
  Satisfactory: { bg: "#84CC16", text: "#fff", ring: "#65A30D" },
  Moderate:     { bg: "#F59E0B", text: "#fff", ring: "#D97706" },
  Poor:         { bg: "#F97316", text: "#fff", ring: "#EA580C" },
  "Very Poor":  { bg: "#EF4444", text: "#fff", ring: "#DC2626" },
  Severe:       { bg: "#7C3AED", text: "#fff", ring: "#6D28D9" },
};

const SOURCE_COLORS = {
  "Vehicle Exhaust":    "#EF4444",
  "Construction Dust":  "#F59E0B",
  "Industrial Stacks":  "#065A82",
  "Biomass Burning":    "#10B981",
  "Secondary Aerosols": "#0D9488",
};

// ── Utility ───────────────────────────────────────────────
function aqiColor(aqi) {
  if (aqi <= 50)  return AQI_COLORS["Good"];
  if (aqi <= 100) return AQI_COLORS["Satisfactory"];
  if (aqi <= 200) return AQI_COLORS["Moderate"];
  if (aqi <= 300) return AQI_COLORS["Poor"];
  if (aqi <= 400) return AQI_COLORS["Very Poor"];
  return AQI_COLORS["Severe"];
}

function aqiCategory(aqi) {
  if (aqi <= 50)  return "Good";
  if (aqi <= 100) return "Satisfactory";
  if (aqi <= 200) return "Moderate";
  if (aqi <= 300) return "Poor";
  if (aqi <= 400) return "Very Poor";
  return "Severe";
}

// ── API helpers ────────────────────────────────────────────
async function apiFetch(path) {
  try {
    const r = await fetch(`${API}${path}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } catch (e) {
    console.warn(`API error ${path}:`, e.message);
    return null;
  }
}

// ── Mock data (shown when API is offline) ─────────────────
function mockDashboard(city) {
  const aqi = { delhi: 218, mumbai: 142, bengaluru: 88,
                kolkata: 175, chennai: 110, hyderabad: 130 }[city] || 150;
  return {
    summary: {
      current_aqi:     aqi,
      aqi_category:    aqiCategory(aqi),
      dominant_source: "Vehicle Exhaust",
      confidence:      0.88,
      pending_actions: 5,
    },
    attribution: {
      current_pm25: Math.round(aqi * 0.4),
      sources: [
        { label: "Vehicle Exhaust",    pct: 38, color: "#EF4444" },
        { label: "Construction Dust",  pct: 22, color: "#F59E0B" },
        { label: "Industrial Stacks",  pct: 18, color: "#065A82" },
        { label: "Biomass Burning",    pct: 14, color: "#10B981" },
        { label: "Secondary Aerosols", pct:  8, color: "#0D9488" },
      ],
      overall_confidence: 0.88,
    },
    forecast_12h: Array.from({ length: 48 }, (_, i) => ({
      hours_ahead:   (i + 1) * 0.25,
      pm25_pred:     Math.max(5, aqi * 0.4 + 20 * Math.sin(i / 6) + (Math.random() - 0.5) * 20),
      aqi_pred:      aqi + 30 * Math.sin(i / 6) + (Math.random() - 0.5) * 40,
      aqi_category:  aqiCategory(aqi),
    })),
    enforcement: [
      { id: "IND001", name: "Bharat Steel Rolling Mill",    type: "industrial",    priority_score: 87, src_contribution_pct: 18, lat: 28.63, lon: 77.21, violations: 3 },
      { id: "VEH001", name: "Old Diesel Bus Depot",         type: "vehicle",       priority_score: 81, src_contribution_pct: 12, lat: 28.64, lon: 77.32, violations: 5 },
      { id: "CON002", name: "DDA Housing Project Sector 9", type: "construction",  priority_score: 72, src_contribution_pct: 10, lat: 28.65, lon: 77.22, violations: 2 },
    ],
    historical_trend: Array.from({ length: 24 }, (_, i) => ({
      hours_ago: (24 - i) * 0.5,
      pm25: Math.max(5, aqi * 0.4 + (Math.random() - 0.5) * 30),
    })),
    advisory: {
      message: `🟠 Air Quality Warning — ${city.charAt(0).toUpperCase() + city.slice(1)}\n\nAQI: ${aqi} (${aqiCategory(aqi)}). Limit outdoor activity. Wear N95 mask if going out. Children and elderly should stay indoors.\n\nMain source: Vehicle exhaust (38%). Consider carpooling today.`,
      severity: aqi > 300 ? "severe" : aqi > 200 ? "very_poor" : "poor",
    },
  };
}

// ═══════════════════════════════════════════════════════════
// COMPONENTS
// ═══════════════════════════════════════════════════════════

// ── AQI Gauge ──────────────────────────────────────────────
function AQIGauge({ aqi, size = 140 }) {
  const col  = aqiColor(aqi);
  const cat  = aqiCategory(aqi);
  const pct  = Math.min(aqi / 500, 1);
  const r    = size * 0.38;
  const circ = 2 * Math.PI * r;
  const dash = circ * pct;

  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <svg width={size} height={size}>
        <circle cx={size/2} cy={size/2} r={r} fill="none"
          stroke="#1e293b" strokeWidth={size * 0.1} />
        <circle cx={size/2} cy={size/2} r={r} fill="none"
          stroke={col.bg} strokeWidth={size * 0.1}
          strokeDasharray={`${dash} ${circ - dash}`}
          strokeLinecap="round"
          transform={`rotate(-90 ${size/2} ${size/2})`}
          style={{ transition: "stroke-dasharray 1s ease" }} />
      </svg>
      <div style={{
        position: "absolute", inset: 0,
        display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center",
      }}>
        <span style={{ fontSize: size * 0.22, fontWeight: 800,
          color: col.bg, lineHeight: 1 }}>{aqi}</span>
        <span style={{ fontSize: size * 0.09, color: "#94a3b8",
          fontWeight: 600, textAlign: "center", marginTop: 2 }}>{cat}</span>
      </div>
    </div>
  );
}

// ── City Selector ──────────────────────────────────────────
function CitySelector({ selected, onChange }) {
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
      {CITIES.map(c => (
        <button key={c} onClick={() => onChange(c)} style={{
          padding: "5px 14px",
          borderRadius: 20,
          border: "none",
          cursor: "pointer",
          fontWeight: 600,
          fontSize: 12,
          background: selected === c ? "#0D9488" : "#0D2137",
          color: selected === c ? "#fff" : "#94a3b8",
          transition: "all 0.2s",
          textTransform: "capitalize",
        }}>{c}</button>
      ))}
    </div>
  );
}

// ── Source Pie ─────────────────────────────────────────────
function SourcePie({ sources, confidence }) {
  const [active, setActive] = useState(null);
  return (
    <div style={{ display: "flex", gap: 20, alignItems: "center", flexWrap: "wrap" }}>
      <ResponsiveContainer width={180} height={180}>
        <PieChart>
          <Pie data={sources} dataKey="pct" cx="50%" cy="50%"
            innerRadius={45} outerRadius={75}
            onMouseEnter={(_, i) => setActive(i)}
            onMouseLeave={() => setActive(null)}>
            {sources.map((s, i) => (
              <Cell key={s.label} fill={s.color}
                opacity={active === null || active === i ? 1 : 0.4}
                stroke="none" />
            ))}
          </Pie>
          <Tooltip formatter={(v) => [`${v}%`, "Contribution"]}
            contentStyle={{ background: "#0A1628", border: "1px solid #1e3a5f",
              borderRadius: 8, color: "#e2f4ff", fontSize: 11 }} />
        </PieChart>
      </ResponsiveContainer>

      <div style={{ flex: 1, minWidth: 140 }}>
        {sources.map((s, i) => (
          <div key={s.label} style={{
            display: "flex", alignItems: "center", gap: 8,
            marginBottom: 7, cursor: "pointer",
            opacity: active === null || active === i ? 1 : 0.5,
          }}
            onMouseEnter={() => setActive(i)}
            onMouseLeave={() => setActive(null)}>
            <div style={{ width: 10, height: 10, borderRadius: 2,
              background: s.color, flexShrink: 0 }} />
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ fontSize: 11, color: "#cbd5e1" }}>{s.label}</span>
                <span style={{ fontSize: 11, fontWeight: 700, color: s.color }}>{s.pct}%</span>
              </div>
              <div style={{ height: 3, background: "#1e3a5f", borderRadius: 2, marginTop: 2 }}>
                <div style={{ height: 3, width: `${s.pct}%`, background: s.color,
                  borderRadius: 2, transition: "width 0.5s ease" }} />
              </div>
            </div>
          </div>
        ))}
        <div style={{ marginTop: 10, padding: "5px 10px",
          background: "#0D2137", borderRadius: 6 }}>
          <span style={{ fontSize: 10, color: "#94a3b8" }}>Attribution confidence: </span>
          <span style={{ fontSize: 10, fontWeight: 700,
            color: confidence > 0.8 ? "#10B981" : "#F59E0B" }}>
            {Math.round(confidence * 100)}%
          </span>
        </div>
      </div>
    </div>
  );
}

// ── Forecast Chart ─────────────────────────────────────────
function ForecastChart({ data }) {
  const hourly = [];
  for (let i = 0; i < data.length; i += 4) {
    const chunk = data.slice(i, i + 4);
    const avgAqi = Math.round(chunk.reduce((s, r) => s + (r.aqi_pred || 200), 0) / chunk.length);
    hourly.push({
      label:    `+${Math.round(chunk[0].hours_ahead)}h`,
      aqi:      avgAqi,
      pm25:     Math.round(chunk.reduce((s, r) => s + (r.pm25_pred || 80), 0) / chunk.length),
      category: aqiCategory(avgAqi),
      color:    aqiColor(avgAqi).bg,
    });
  }

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={hourly} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e3a5f" />
        <XAxis dataKey="label" tick={{ fill: "#94a3b8", fontSize: 10 }} />
        <YAxis tick={{ fill: "#94a3b8", fontSize: 10 }} domain={[0, 500]} />
        <Tooltip
          contentStyle={{ background: "#0D2137", border: "1px solid #1e3a5f",
            borderRadius: 8, color: "#e2f4ff", fontSize: 11 }}
          formatter={(v, n) => [v, n === "aqi" ? "AQI" : "PM2.5 µg/m³"]}
        />
        <Bar dataKey="aqi" radius={[3, 3, 0, 0]}>
          {hourly.map((h, i) => <Cell key={i} fill={h.color} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ── Trend Chart ────────────────────────────────────────────
function TrendChart({ data }) {
  const formatted = [...data].reverse().map((d, i) => ({
    label: `-${Math.round(d.hours_ago * 2) / 2}h`,
    pm25:  Math.round(d.pm25),
  }));

  return (
    <ResponsiveContainer width="100%" height={100}>
      <LineChart data={formatted} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e3a5f" />
        <XAxis dataKey="label" tick={{ fill: "#94a3b8", fontSize: 9 }}
          interval={5} />
        <YAxis tick={{ fill: "#94a3b8", fontSize: 9 }} />
        <Tooltip contentStyle={{ background: "#0D2137", border: "1px solid #1e3a5f",
          borderRadius: 8, color: "#e2f4ff", fontSize: 11 }} />
        <Line type="monotone" dataKey="pm25" stroke="#0D9488"
          strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ── Enforcement Card ───────────────────────────────────────
function EnforcementCard({ action, rank }) {
  const [expanded, setExpanded] = useState(false);
  const typeColor = {
    industrial:   "#065A82",
    construction: "#F59E0B",
    vehicle:      "#EF4444",
    biomass:      "#10B981",
  }[action.type] || "#888";

  const urgency = action.priority_score > 80 ? "HIGH" :
                  action.priority_score > 60 ? "MED"  : "LOW";
  const urgencyColor = urgency === "HIGH" ? "#EF4444" :
                       urgency === "MED"  ? "#F59E0B" : "#10B981";

  return (
    <div style={{
      background: "#0D2137", borderRadius: 10, padding: "12px 14px",
      marginBottom: 8, border: `1px solid ${urgency === "HIGH" ? "#EF444433" : "#1e3a5f"}`,
      cursor: "pointer",
    }} onClick={() => setExpanded(!expanded)}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{
          width: 26, height: 26, borderRadius: 13,
          background: "#0A1628", display: "flex", alignItems: "center",
          justifyContent: "center", fontSize: 11, fontWeight: 800,
          color: "#94a3b8", flexShrink: 0,
        }}>#{rank}</div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", justifyContent: "space-between",
            alignItems: "center" }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: "#e2f4ff",
              overflow: "hidden", textOverflow: "ellipsis",
              whiteSpace: "nowrap", maxWidth: "65%" }}>
              {action.name}
            </span>
            <span style={{ fontSize: 10, fontWeight: 700, color: urgencyColor,
              background: urgencyColor + "22", padding: "2px 7px",
              borderRadius: 10, flexShrink: 0 }}>{urgency}</span>
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 3 }}>
            <span style={{ fontSize: 10, color: typeColor,
              background: typeColor + "22", padding: "1px 6px",
              borderRadius: 8, textTransform: "capitalize" }}>
              {action.type}
            </span>
            <span style={{ fontSize: 10, color: "#94a3b8" }}>
              Score: {action.priority_score} · {action.violations} prior violations
            </span>
          </div>
        </div>
      </div>

      {expanded && (
        <div style={{ marginTop: 12, paddingTop: 10,
          borderTop: "1px solid #1e3a5f" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr",
            gap: 8, marginBottom: 10 }}>
            {[
              ["Source contribution", `${action.src_contribution_pct}%`],
              ["Priority score",      action.priority_score],
              ["GPS",                 `${action.lat?.toFixed(3)}, ${action.lon?.toFixed(3)}`],
              ["Prior violations",    action.violations],
            ].map(([k, v]) => (
              <div key={k} style={{ background: "#0A1628", borderRadius: 6, padding: "6px 8px" }}>
                <div style={{ fontSize: 9, color: "#94a3b8" }}>{k}</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#e2f4ff" }}>{v}</div>
              </div>
            ))}
          </div>
          <button style={{
            width: "100%", padding: "8px",
            background: "linear-gradient(135deg, #065A82, #0D9488)",
            color: "#fff", border: "none", borderRadius: 7,
            fontSize: 12, fontWeight: 700, cursor: "pointer",
          }}>
            📤 Dispatch Inspector + Send Notice
          </button>
        </div>
      )}
    </div>
  );
}

// ── Chatbot ────────────────────────────────────────────────
function Chatbot({ city }) {
  const [messages, setMessages] = useState([{
    role: "bot",
    text: `🌬️ Hello! I'm VAYU, your air quality assistant for ${city}.\nAsk me anything — in Hindi, English, or any Indian language.\n\nTry: "Kal hawa kaisi rahegi?" or "Is it safe to exercise tomorrow morning?"`,
  }]);
  const [input, setInput]     = useState("");
  const [loading, setLoading] = useState(false);

  const send = async () => {
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setInput("");
    setMessages(m => [...m, { role: "user", text: userMsg }]);
    setLoading(true);

    try {
      const data = await apiFetch("/chatbot");
      // Direct POST
      const res = await fetch(`${API}/chatbot`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ message: userMsg, city }),
      });
      const json = await res.json();
      setMessages(m => [...m, { role: "bot", text: json.reply || "Sorry, no response." }]);
    } catch {
      setMessages(m => [...m, {
        role: "bot",
        text: `🌬️ AQI update for ${city}: Currently Moderate (AQI ~180). Tomorrow morning looks similar — wearing a mask for outdoor activities is advisable.`,
      }]);
    }
    setLoading(false);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: 10 }}>
      <div style={{
        flex: 1, overflowY: "auto", display: "flex",
        flexDirection: "column", gap: 8, paddingRight: 4,
        minHeight: 0,
      }}>
        {messages.map((m, i) => (
          <div key={i} style={{
            display: "flex",
            justifyContent: m.role === "user" ? "flex-end" : "flex-start",
          }}>
            <div style={{
              maxWidth: "82%",
              background: m.role === "user" ? "#065A82" : "#0D2137",
              color: "#e2f4ff",
              borderRadius: m.role === "user" ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
              padding: "10px 13px",
              fontSize: 12,
              lineHeight: 1.55,
              whiteSpace: "pre-wrap",
              border: m.role === "bot" ? "1px solid #1e3a5f" : "none",
            }}>{m.text}</div>
          </div>
        ))}
        {loading && (
          <div style={{ display: "flex" }}>
            <div style={{ background: "#0D2137", borderRadius: "16px 16px 16px 4px",
              padding: "10px 14px", border: "1px solid #1e3a5f",
              fontSize: 12, color: "#94a3b8" }}>
              ⏳ Thinking...
            </div>
          </div>
        )}
      </div>

      <div style={{ display: "flex", gap: 8 }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && send()}
          placeholder="Ask about air quality in any language..."
          style={{
            flex: 1, background: "#0D2137", border: "1px solid #1e3a5f",
            borderRadius: 10, padding: "10px 14px", color: "#e2f4ff",
            fontSize: 12, outline: "none",
          }}
        />
        <button onClick={send} style={{
          background: "linear-gradient(135deg, #065A82, #0D9488)",
          color: "#fff", border: "none", borderRadius: 10,
          padding: "10px 16px", cursor: "pointer",
          fontSize: 14, fontWeight: 700,
        }}>→</button>
      </div>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {[
          "Kal hawa kaisi rahegi?",
          "Safe for morning walk?",
          "Main sources today?",
          "AQI forecast 48h",
        ].map(q => (
          <button key={q} onClick={() => { setInput(q); }} style={{
            background: "#0D2137", border: "1px solid #1e3a5f",
            borderRadius: 14, padding: "4px 10px", color: "#94a3b8",
            fontSize: 10, cursor: "pointer",
          }}>{q}</button>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// MAIN APP
// ═══════════════════════════════════════════════════════════
export default function App() {
  const [city,    setCity]    = useState("delhi");
  const [tab,     setTab]     = useState("overview");
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [apiLive, setApiLive] = useState(false);

  const loadData = useCallback(async (c) => {
    setLoading(true);
    const result = await apiFetch(`/dashboard/${c}`);
    if (result) {
      setData(result);
      setApiLive(true);
    } else {
      setData(mockDashboard(c));
      setApiLive(false);
    }
    setLoading(false);
  }, []);

  useEffect(() => { loadData(city); }, [city, loadData]);

  // Auto-refresh every 5 minutes
  useEffect(() => {
    const id = setInterval(() => loadData(city), 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [city, loadData]);

  const S = data?.summary || {};
  const attr = data?.attribution || {};
  const aqi  = S.current_aqi || 200;
  const col  = aqiColor(aqi);

  const TABS = [
    { id: "overview",    label: "Overview" },
    { id: "attribution", label: "Attribution" },
    { id: "forecast",    label: "Forecast" },
    { id: "enforcement", label: "Enforcement" },
    { id: "chatbot",     label: "Chatbot" },
  ];

  return (
    <div style={{
      minHeight: "100vh",
      background: "#0A1628",
      color: "#e2f4ff",
      fontFamily: "'Segoe UI', system-ui, sans-serif",
      fontSize: 13,
    }}>
      {/* ── Header ── */}
      <div style={{
        background: "#0D2137",
        borderBottom: "1px solid #1e3a5f",
        padding: "12px 20px",
        display: "flex",
        alignItems: "center",
        gap: 16,
        flexWrap: "wrap",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 34, height: 34, borderRadius: 8,
            background: "linear-gradient(135deg, #065A82, #0D9488)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 16,
          }}>🌬️</div>
          <div>
            <div style={{ fontWeight: 800, fontSize: 16, color: "#fff",
              letterSpacing: 0.5 }}>VAYU</div>
            <div style={{ fontSize: 9, color: "#94a3b8", letterSpacing: 1 }}>
              AIR QUALITY INTELLIGENCE
            </div>
          </div>
        </div>

        <CitySelector selected={city} onChange={(c) => {
          setCity(c); setTab("overview");
        }} />

        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{
            width: 7, height: 7, borderRadius: 4,
            background: apiLive ? "#10B981" : "#F59E0B",
            boxShadow: `0 0 6px ${apiLive ? "#10B981" : "#F59E0B"}`,
          }} />
          <span style={{ fontSize: 10, color: "#94a3b8" }}>
            {apiLive ? "Live API" : "Demo Mode"}
          </span>
          <button onClick={() => loadData(city)} style={{
            background: "#1e3a5f", border: "none", borderRadius: 6,
            color: "#94a3b8", padding: "4px 10px", cursor: "pointer", fontSize: 10,
          }}>↻ Refresh</button>
        </div>
      </div>

      {/* ── Tabs ── */}
      <div style={{
        display: "flex", gap: 2, padding: "10px 20px 0",
        borderBottom: "1px solid #1e3a5f",
      }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            padding: "7px 16px",
            background: "none",
            border: "none",
            borderBottom: tab === t.id ? `2px solid #0D9488` : "2px solid transparent",
            color: tab === t.id ? "#0D9488" : "#94a3b8",
            cursor: "pointer",
            fontWeight: tab === t.id ? 700 : 400,
            fontSize: 12,
            transition: "all 0.2s",
          }}>{t.label}</button>
        ))}
      </div>

      {/* ── Body ── */}
      <div style={{ padding: "16px 20px", maxWidth: 1200, margin: "0 auto" }}>

        {loading ? (
          <div style={{ textAlign: "center", padding: "60px 0", color: "#94a3b8" }}>
            <div style={{ fontSize: 32, marginBottom: 10 }}>🌬️</div>
            <div>Loading {city} air quality data...</div>
          </div>
        ) : (

          <>
            {/* ════ OVERVIEW TAB ════ */}
            {tab === "overview" && (
              <div style={{ display: "grid", gap: 14,
                gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>

                {/* AQI Gauge Card */}
                <div style={{
                  background: "#0D2137", borderRadius: 14,
                  padding: 20, gridColumn: "span 1",
                  border: `1px solid ${col.bg}33`,
                  display: "flex", flexDirection: "column", gap: 12,
                }}>
                  <div style={{ fontSize: 11, fontWeight: 700,
                    color: "#94a3b8", textTransform: "uppercase",
                    letterSpacing: 1 }}>
                    Current AQI — {city.charAt(0).toUpperCase() + city.slice(1)}
                  </div>
                  <div style={{ display: "flex", alignItems: "center",
                    gap: 20, justifyContent: "center" }}>
                    <AQIGauge aqi={aqi} size={140} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 10, color: "#94a3b8" }}>PM2.5</div>
                      <div style={{ fontSize: 24, fontWeight: 800,
                        color: col.bg }}>{attr.current_pm25 || Math.round(aqi * 0.4)} µg/m³</div>
                      <div style={{ marginTop: 8, fontSize: 10, color: "#94a3b8" }}>
                        Main source
                      </div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "#e2f4ff" }}>
                        {S.dominant_source || "Vehicle Exhaust"}
                      </div>
                      <div style={{ marginTop: 8, fontSize: 10, color: "#94a3b8" }}>
                        Confidence
                      </div>
                      <div style={{ fontSize: 13, fontWeight: 700,
                        color: (S.confidence || 0) > 0.8 ? "#10B981" : "#F59E0B" }}>
                        {Math.round((S.confidence || 0.8) * 100)}%
                      </div>
                    </div>
                  </div>
                </div>

                {/* Attribution Pie Card */}
                <div style={{ background: "#0D2137", borderRadius: 14, padding: 20,
                  border: "1px solid #1e3a5f" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8",
                    textTransform: "uppercase", letterSpacing: 1, marginBottom: 12 }}>
                    Source Attribution
                  </div>
                  {attr.sources && (
                    <SourcePie sources={attr.sources}
                      confidence={attr.overall_confidence || 0.88} />
                  )}
                </div>

                {/* Trend + Forecast Card */}
                <div style={{ background: "#0D2137", borderRadius: 14, padding: 20,
                  border: "1px solid #1e3a5f",
                  gridColumn: "span 1" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8",
                    textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>
                    12-Hour Trend
                  </div>
                  <TrendChart data={data.historical_trend || []} />
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8",
                    textTransform: "uppercase", letterSpacing: 1,
                    marginTop: 14, marginBottom: 8 }}>
                    12-Hour Forecast
                  </div>
                  <ForecastChart data={data.forecast_12h || []} />
                </div>

                {/* Stats row */}
                <div style={{
                  gridColumn: "1 / -1",
                  display: "grid", gap: 10,
                  gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
                }}>
                  {[
                    { label: "AQI",           value: aqi,                           unit: "",     color: col.bg },
                    { label: "PM2.5",         value: attr.current_pm25 || Math.round(aqi*0.4), unit: " µg/m³", color: "#0D9488" },
                    { label: "Confidence",    value: `${Math.round((S.confidence||0.88)*100)}%`, unit: "", color: "#10B981" },
                    { label: "Actions Pending", value: S.pending_actions || 5,     unit: "",     color: "#F59E0B" },
                  ].map(stat => (
                    <div key={stat.label} style={{
                      background: "#0D2137", borderRadius: 10, padding: "14px 16px",
                      border: "1px solid #1e3a5f",
                    }}>
                      <div style={{ fontSize: 10, color: "#94a3b8", marginBottom: 4 }}>
                        {stat.label}
                      </div>
                      <div style={{ fontSize: 26, fontWeight: 800, color: stat.color }}>
                        {stat.value}{stat.unit}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Advisory */}
                {data.advisory?.message && (
                  <div style={{
                    gridColumn: "1 / -1",
                    background: "#0D2137", borderRadius: 14, padding: 16,
                    border: "1px solid #1e3a5f",
                  }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8",
                      textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>
                      Citizen Advisory
                    </div>
                    <pre style={{ fontFamily: "inherit", fontSize: 12,
                      color: "#e2f4ff", whiteSpace: "pre-wrap", margin: 0 }}>
                      {data.advisory.message}
                    </pre>
                  </div>
                )}
              </div>
            )}

            {/* ════ ATTRIBUTION TAB ════ */}
            {tab === "attribution" && (
              <div style={{ display: "grid", gap: 14,
                gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
                <div style={{ background: "#0D2137", borderRadius: 14, padding: 20,
                  border: "1px solid #1e3a5f", gridColumn: "span 2" }}>
                  <div style={{ fontSize: 16, fontWeight: 800, color: "#fff",
                    marginBottom: 4 }}>
                    Source Attribution — {city.charAt(0).toUpperCase() + city.slice(1)}
                  </div>
                  <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 16 }}>
                    Cross-modal fusion: CAAQMS · Sentinel-5P · Traffic · Construction permits · Wind backtracking
                  </div>
                  {attr.sources && (
                    <SourcePie sources={attr.sources}
                      confidence={attr.overall_confidence || 0.88} />
                  )}
                </div>

                {/* Source detail cards */}
                {(attr.sources || []).map(s => (
                  <div key={s.label} style={{
                    background: "#0D2137", borderRadius: 12, padding: 16,
                    border: `1px solid ${s.color}33`,
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between",
                      alignItems: "center", marginBottom: 10 }}>
                      <span style={{ fontSize: 13, fontWeight: 700,
                        color: s.color }}>{s.label}</span>
                      <span style={{ fontSize: 24, fontWeight: 800,
                        color: s.color }}>{s.pct}%</span>
                    </div>
                    <div style={{ height: 6, background: "#1e3a5f", borderRadius: 3 }}>
                      <div style={{ height: 6, width: `${s.pct}%`,
                        background: s.color, borderRadius: 3,
                        transition: "width 1s ease" }} />
                    </div>
                    <div style={{ fontSize: 10, color: "#94a3b8", marginTop: 8 }}>
                      {{
                        "Vehicle Exhaust":    "Diesel trucks, old buses, 2-wheelers",
                        "Construction Dust":  "Cement, RMC plants, unpaved roads",
                        "Industrial Stacks":  "Power plants, brick kilns, industries",
                        "Biomass Burning":    "Crop residue, waste burning, biomass",
                        "Secondary Aerosols": "Atmospheric chemical formation",
                      }[s.label] || "Mixed sources"}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* ════ FORECAST TAB ════ */}
            {tab === "forecast" && (
              <div style={{ display: "grid", gap: 14 }}>
                <div style={{ background: "#0D2137", borderRadius: 14, padding: 20,
                  border: "1px solid #1e3a5f" }}>
                  <div style={{ fontSize: 16, fontWeight: 800, color: "#fff",
                    marginBottom: 4 }}>
                    48-Hour AQI Forecast — {city.charAt(0).toUpperCase() + city.slice(1)}
                  </div>
                  <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 16 }}>
                    BiLSTM ensemble · 1 km² ward resolution · Updated every 15 min
                  </div>
                  <ForecastChart data={data.forecast_12h || []} />
                </div>

                {/* Hourly table */}
                <div style={{ background: "#0D2137", borderRadius: 14, padding: 20,
                  border: "1px solid #1e3a5f", overflowX: "auto" }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#fff",
                    marginBottom: 12 }}>Hourly Detail</div>
                  <table style={{ width: "100%", borderCollapse: "collapse",
                    fontSize: 11 }}>
                    <thead>
                      <tr style={{ color: "#94a3b8" }}>
                        {["Hour", "PM2.5 µg/m³", "AQI", "Category"].map(h => (
                          <th key={h} style={{ padding: "6px 12px", textAlign: "left",
                            borderBottom: "1px solid #1e3a5f" }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(data.forecast_12h || [])
                        .filter((_, i) => i % 4 === 0)
                        .map((row, i) => {
                          const c = aqiColor(row.aqi_pred || 200);
                          return (
                            <tr key={i} style={{
                              background: i % 2 === 0 ? "#0A162888" : "transparent" }}>
                              <td style={{ padding: "7px 12px", color: "#e2f4ff" }}>
                                +{Math.round(row.hours_ahead)}h
                              </td>
                              <td style={{ padding: "7px 12px", color: "#0D9488",
                                fontWeight: 700 }}>
                                {Math.round(row.pm25_pred || 80)}
                              </td>
                              <td style={{ padding: "7px 12px", color: c.bg,
                                fontWeight: 700 }}>
                                {Math.round(row.aqi_pred || 200)}
                              </td>
                              <td style={{ padding: "7px 12px" }}>
                                <span style={{ background: c.bg + "22",
                                  color: c.bg, padding: "2px 8px",
                                  borderRadius: 10, fontWeight: 600,
                                  fontSize: 10 }}>
                                  {row.aqi_category || aqiCategory(row.aqi_pred || 200)}
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* ════ ENFORCEMENT TAB ════ */}
            {tab === "enforcement" && (
              <div style={{ display: "grid", gap: 14,
                gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))" }}>
                <div style={{ gridColumn: "1 / -1" }}>
                  <div style={{ fontSize: 16, fontWeight: 800, color: "#fff",
                    marginBottom: 4 }}>
                    Enforcement Action Queue — {city.charAt(0).toUpperCase() + city.slice(1)}
                  </div>
                  <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 16 }}>
                    Ranked by: source contribution × recidivism × forecast urgency
                    · Tap any entry to expand evidence and dispatch
                  </div>
                </div>

                <div>
                  {(data.enforcement || []).map((a, i) => (
                    <EnforcementCard key={a.id} action={a} rank={i + 1} />
                  ))}
                </div>

                <div style={{ background: "#0D2137", borderRadius: 14, padding: 16,
                  border: "1px solid #1e3a5f", height: "fit-content" }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#F59E0B",
                    marginBottom: 12 }}>Today's Stats</div>
                  {[
                    ["Inspections dispatched", "3"],
                    ["Notices auto-drafted",   "3"],
                    ["Avg response time",       "8 min"],
                    ["Inspector hours saved",  "~4.5h"],
                  ].map(([k, v]) => (
                    <div key={k} style={{ display: "flex", justifyContent: "space-between",
                      padding: "7px 0", borderBottom: "1px solid #1e3a5f" }}>
                      <span style={{ fontSize: 11, color: "#94a3b8" }}>{k}</span>
                      <span style={{ fontSize: 11, fontWeight: 700, color: "#e2f4ff" }}>{v}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ════ CHATBOT TAB ════ */}
            {tab === "chatbot" && (
              <div style={{ display: "grid", gap: 14,
                gridTemplateColumns: "3fr 2fr" }}>
                <div style={{ background: "#0D2137", borderRadius: 14, padding: 16,
                  border: "1px solid #1e3a5f", height: 520,
                  display: "flex", flexDirection: "column" }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#fff",
                    marginBottom: 12 }}>
                    🌬️ VAYU Citizen Assistant
                    <span style={{ fontSize: 10, color: "#94a3b8",
                      fontWeight: 400, marginLeft: 8 }}>
                      Answers in your language
                    </span>
                  </div>
                  <Chatbot city={city} />
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <div style={{ background: "#0D2137", borderRadius: 14, padding: 16,
                    border: "1px solid #1e3a5f" }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "#0D9488",
                      marginBottom: 10 }}>12 Languages</div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {[
                        ["hi", "हिंदी"], ["en", "English"], ["bn", "বাংলা"],
                        ["te", "తెలుగు"], ["mr", "मराठी"], ["ta", "தமிழ்"],
                        ["gu", "ગુજરાતી"], ["kn", "ಕನ್ನಡ"], ["ml", "മലയാളം"],
                        ["pa", "ਪੰਜਾਬੀ"], ["or", "ଓଡ଼ିଆ"], ["ur", "اردو"],
                      ].map(([code, name]) => (
                        <span key={code} style={{
                          background: "#0A1628", border: "1px solid #1e3a5f",
                          borderRadius: 8, padding: "3px 8px",
                          fontSize: 11, color: "#e2f4ff",
                        }}>{name}</span>
                      ))}
                    </div>
                  </div>

                  <div style={{ background: "#0D2137", borderRadius: 14, padding: 16,
                    border: "1px solid #1e3a5f" }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "#F59E0B",
                      marginBottom: 10 }}>Channels</div>
                    {[
                      ["💬 WhatsApp", "wa.me/919XXXXXXXX", true],
                      ["📞 IVR Hotline", "1800-XXX-VAYU",   true],
                      ["📱 Mobile App", "vayu.gov.in/app",  false],
                    ].map(([ch, val, live]) => (
                      <div key={ch} style={{ display: "flex", justifyContent: "space-between",
                        alignItems: "center", padding: "7px 0",
                        borderBottom: "1px solid #1e3a5f" }}>
                        <span style={{ fontSize: 11, color: "#e2f4ff" }}>{ch}</span>
                        <div style={{ textAlign: "right" }}>
                          <div style={{ fontSize: 10, color: "#94a3b8" }}>{val}</div>
                          <span style={{ fontSize: 9, color: live ? "#10B981" : "#F59E0B",
                            fontWeight: 700 }}>{live ? "● LIVE" : "● COMING SOON"}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
