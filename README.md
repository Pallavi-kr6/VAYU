# VAYU — Urban Air Quality Intelligence Platform
## ET AI Hackathon 2026 | Problem Statement #5

Complete end-to-end implementation: data pipeline → model training → multi-agent backend → dashboard.

## Project Structure
```
vayu/
├── config/             # Environment & model config
├── data/               # Data download & preprocessing scripts  
├── models/             # ML model training (AQI forecast + attribution)
├── agents/             # Multi-agent AI system (5 agents)
├── api/                # FastAPI backend
├── frontend/           # React dashboard
├── notebooks/          # Jupyter EDA notebooks
└── scripts/            # Run scripts
```

## Quick Start (Local Demo)
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Download & prepare data
python data/download_data.py
python data/preprocess.py

# 3. Train models
python models/train_attribution.py
python models/train_forecast.py

# 4. Start backend API
uvicorn api.main:app --reload --port 8000

# 5. Start frontend
cd frontend && npm install && npm start
```
