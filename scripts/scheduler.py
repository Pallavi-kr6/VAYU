# scripts/scheduler.py
# ─────────────────────────────────────────────────────────
# Background scheduler — refreshes all city data every 15 min.
# In production: replace with Apache Airflow DAG.
# For demo: run this alongside the API.
# ─────────────────────────────────────────────────────────

import sys, time
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import schedule
from loguru import logger
from datetime import datetime

from agents.vayu_agents import VAYUOrchestrator
from data.download_data import fetch_openweather_live, generate_live_synthetic
from config.settings import CITIES, OPENWEATHER_API_KEY

orchestrator = VAYUOrchestrator()


def refresh_all_cities():
    """Pull latest data and re-run pipeline for all cities."""
    logger.info(f"⏰ Scheduled refresh — {datetime.utcnow().strftime('%H:%M:%S UTC')}")
    for city in CITIES:
        try:
            df = fetch_openweather_live(city, api_key=OPENWEATHER_API_KEY)
            orchestrator.run_city(city, df)
            logger.info(f"  ✓ {city}")
        except Exception as e:
            logger.error(f"  ✗ {city}: {e}")

    orchestrator.comparative_agent.run()
    logger.success("Refresh complete")


if __name__ == "__main__":
    logger.info("VAYU Scheduler starting...")
    refresh_all_cities()   # Run immediately on start

    schedule.every(15).minutes.do(refresh_all_cities)

    logger.info("Scheduler running (every 15 min). Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(60)
