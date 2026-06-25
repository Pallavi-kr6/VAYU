#!/bin/bash
# scripts/run_demo.sh
# ─────────────────────────────────────────────────────────
# VAYU — One-click Hackathon Demo Runner
# Run this script to start everything for the demo.
# ─────────────────────────────────────────────────────────

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  🌬️  VAYU — Urban Air Quality Intelligence       ║"
echo "║      ET AI Hackathon 2026 | Problem #5           ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── 1. Check Python ────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "❌ Python 3 not found. Install Python 3.10+ first."
    exit 1
fi
echo "✓ Python: $(python3 --version)"

# ── 2. Virtual environment ────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate
echo "✓ Virtual environment active"

# ── 3. Install dependencies ───────────────────────────────
echo "Installing Python dependencies (first run takes ~3 min)..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "✓ Dependencies installed"

# ── 4. Setup .env if not exists ───────────────────────────
if [ ! -f ".env" ]; then
    cat > .env << 'ENV'
# VAYU Environment Variables
# Fill in your actual keys before demo

GROQ_API_KEY=                       # Required for chatbot & notices
                                    # Get free at: console.groq.com

OPENWEATHER_API_KEY=                # Required for live AQI data
                                    # Get free at: openweathermap.org/api
                                    # Free tier: 1000 calls/day — enough for all cities

GEE_PROJECT=                        # Optional: Google Earth Engine project
                                    # For Sentinel-5P satellite data

TWILIO_ACCOUNT_SID=                 # Optional: WhatsApp integration
TWILIO_AUTH_TOKEN=                  # Optional: WhatsApp integration
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

SUPABASE_URL=                         # https://supabase.com/dashboard
SUPABASE_ANON_KEY=                    # Project Settings → API → anon key
SUPABASE_SERVICE_KEY=                 # Project Settings → API → service_role key
ENV
    echo "✓ Created .env file — add your API keys"
fi

# ── 5. Generate data ──────────────────────────────────────
echo ""
echo "Generating demo data..."
python3 -c "
import sys; sys.path.insert(0, '.')
from data.download_data import create_synthetic_aqi_data
from pathlib import Path
out = Path('data/raw/aqi_india_2015_2024')
out.mkdir(parents=True, exist_ok=True)
create_synthetic_aqi_data(out, 'aqi_india_2015_2024')
print('✓ Demo data generated')
"

# ── 6. Run option ─────────────────────────────────────────
echo ""
echo "What do you want to run?"
echo "  [1] Streamlit Demo (recommended for hackathon)"
echo "  [2] FastAPI Backend only"
echo "  [3] Full stack (FastAPI + React)"
echo "  [4] Train models (runs data download + training)"
echo ""
read -p "Enter choice [1-4, default=1]: " choice
choice=${choice:-1}

if [ "$choice" == "1" ]; then
    echo ""
    echo "🚀 Starting Streamlit demo..."
    echo "   Open: http://localhost:8501"
    echo ""
    streamlit run streamlit_app.py \
        --server.port 8501 \
        --server.address 0.0.0.0 \
        --theme.base dark \
        --theme.backgroundColor "#0A1628" \
        --theme.secondaryBackgroundColor "#0D2137" \
        --theme.textColor "#e2f4ff" \
        --theme.primaryColor "#0D9488"

elif [ "$choice" == "2" ]; then
    echo ""
    echo "🚀 Starting FastAPI backend..."
    echo "   API: http://localhost:8000"
    echo "   Docs: http://localhost:8000/docs"
    echo ""
    uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

elif [ "$choice" == "3" ]; then
    echo ""
    echo "🚀 Starting full stack..."
    # Start API in background
    uvicorn api.main:app --host 0.0.0.0 --port 8000 &
    API_PID=$!
    echo "✓ API started (PID: $API_PID)"
    sleep 2

    # Start React frontend
    cd frontend
    if [ ! -d "node_modules" ]; then
        echo "Installing Node.js dependencies..."
        npm install
    fi
    echo "✓ Starting React dashboard..."
    echo "   Dashboard: http://localhost:3000"
    npm start &
    REACT_PID=$!

    trap "kill $API_PID $REACT_PID 2>/dev/null" EXIT
    wait

elif [ "$choice" == "4" ]; then
    echo ""
    echo "📊 Running full training pipeline..."
    echo ""
    echo "Step 1/4: Downloading data..."
    python3 data/download_data.py

    echo "Step 2/4: Preprocessing..."
    python3 data/preprocess.py

    echo "Step 3/4: Training attribution model..."
    python3 models/train_attribution.py

    echo "Step 4/4: Training forecast model..."
    python3 models/train_forecast.py

    echo ""
    echo "✅ Training complete! Run script again and choose [1] for demo."
fi
