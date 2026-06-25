@echo off
REM scripts/run_demo.bat — Windows one-click launcher
REM ─────────────────────────────────────────────────────────

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║  VAYU — Urban Air Quality Intelligence           ║
echo ║  ET AI Hackathon 2026 ^| Problem #5              ║
echo ╚══════════════════════════════════════════════════╝
echo.

cd /d "%~dp0.."

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10+ first.
    pause & exit /b 1
)

REM Virtual environment
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)
call .venv\Scripts\activate.bat

REM Install deps
echo Installing dependencies...
pip install -q --upgrade pip
pip install -q -r requirements.txt

REM Create .env if missing
if not exist ".env" (
    echo GROQ_API_KEY=> .env
    echo OPENWEATHER_API_KEY=>> .env
    echo TWILIO_ACCOUNT_SID=>> .env
    echo TWILIO_AUTH_TOKEN=>> .env
    echo SUPABASE_URL=>> .env
    echo SUPABASE_ANON_KEY=>> .env
    echo SUPABASE_SERVICE_KEY=>> .env
    echo Created .env — add your API keys
)

REM Generate demo data
python -c "import sys; sys.path.insert(0,'.'); from pathlib import Path; from data.download_data import create_synthetic_aqi_data; out=Path('data/raw/aqi_india_2015_2024'); out.mkdir(parents=True,exist_ok=True); create_synthetic_aqi_data(out,'demo')"

echo.
echo Starting Streamlit demo...
echo Open: http://localhost:8501
echo.
streamlit run streamlit_app.py --server.port 8501 --theme.base dark
pause
