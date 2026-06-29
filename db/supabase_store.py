# db/supabase_store.py
# ─────────────────────────────────────────────────────────
# Supabase persistence for VAYU agent outputs & logs.
# Falls back gracefully when SUPABASE_URL / key are unset.
# ─────────────────────────────────────────────────────────

from datetime import datetime, date
from typing import Any, Optional

import numpy as np
import pandas as pd
from loguru import logger

_client = None


def _json_safe(obj):
    """Recursively convert pandas/numpy objects into JSON-serializable types."""

    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]

    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()

    if isinstance(obj, np.integer):
        return int(obj)

    if isinstance(obj, np.floating):
        return float(obj)

    if isinstance(obj, np.bool_):
        return bool(obj)

    if isinstance(obj, np.ndarray):
        return obj.tolist()

    if pd.isna(obj):
        return None

    return obj


def get_client():
    """Lazy singleton Supabase client."""

    global _client

    if _client is not None:
        return _client

    from config.settings import SUPABASE_URL, SUPABASE_SERVICE_KEY

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return None

    try:
        from supabase import create_client

        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        return _client

    except Exception as e:
        logger.warning(f"Supabase client init failed: {e}")
        return None


class SupabaseStore:

    CACHE_TABLE = "agent_cache"

    @staticmethod
    def is_configured() -> bool:
        return get_client() is not None

    @staticmethod
    def set(key: str, value: Any) -> bool:
        client = get_client()

        if not client:
            return False

        try:
            client.table(SupabaseStore.CACHE_TABLE).upsert({
                "key": key,
                "data": _json_safe(value),
                "updated_at": datetime.utcnow().isoformat(),
            }).execute()

            return True

        except Exception as e:
            logger.warning(f"Supabase write failed ({key}): {e}")
            return False

    @staticmethod
    def get(key: str) -> Optional[Any]:
        client = get_client()

        if not client:
            return None

        try:
            resp = (
                client.table(SupabaseStore.CACHE_TABLE)
                .select("data")
                .eq("key", key)
                .limit(1)
                .execute()
            )

            if resp.data:
                return resp.data[0]["data"]

        except Exception as e:
            logger.warning(f"Supabase read failed ({key}): {e}")

        return None

    @staticmethod
    def load_all() -> dict[str, dict]:
        client = get_client()

        if not client:
            return {}

        try:
            resp = (
                client.table(SupabaseStore.CACHE_TABLE)
                .select("*")
                .execute()
            )

            cache = {}

            for row in resp.data or []:
                cache[row["key"]] = row["data"]

            return cache

        except Exception as e:
            logger.warning(f"Supabase cache load failed: {e}")
            return {}

    @staticmethod
    def get_polluters(city: Optional[str] = None) -> list[dict]:
        client = get_client()

        if not client:
            return []

        try:
            query = client.table("polluters").select("*")

            if city:
                query = query.or_(f"city.eq.{city},city.is.null")

            resp = query.execute()

            return resp.data or []

        except Exception as e:
            logger.warning(f"Supabase polluters read failed: {e}")
            return []

    @staticmethod
    def log_chat(
        city: str,
        role: str,
        message: str,
        phone: Optional[str] = None,
    ) -> None:

        client = get_client()

        if not client:
            return

        try:
            client.table("chat_logs").insert({
                "city": city,
                "phone": phone,
                "role": role,
                "message": message,
            }).execute()

        except Exception as e:
            logger.warning(f"Supabase chat log failed: {e}")

    @staticmethod
    def save_reading(
        city: str,
        pm25: float,
        pm10: float,
        aqi: int,
        pollutants: Optional[dict] = None,
        temp: float = None,
        humidity: float = None,
        pressure: float = None,
        wind_speed: float = None,
        wind_dir: float = None,
        rainfall: float = None,
    ) -> None:

        client = get_client()

        if not client:
            return

        try:
            client.table("city_readings").insert({
                "city": city,
                "pm25": pm25,
                "pm10": pm10,
                "aqi": aqi,
                "temp": temp,
                "humidity": humidity,
                "pressure": pressure,
                "wind_speed": wind_speed,
                "wind_dir": wind_dir,
                "rainfall": rainfall,
                "pollutants": _json_safe(pollutants or {}),
            }).execute()

        except Exception as e:
            logger.warning(f"Supabase city_readings insert failed: {e}")

    @staticmethod
    def get_recent_readings(
        city: str,
        limit: int = 96,
    ) -> pd.DataFrame:

        client = get_client()

        if not client:
            return pd.DataFrame()

        try:
            resp = (
                client.table("city_readings")
                .select("*")
                .eq("city", city)
                .order("recorded_at", desc=True)
                .limit(limit)
                .execute()
            )

            df = pd.DataFrame(resp.data or [])

            if not df.empty:
                df["recorded_at"] = pd.to_datetime(df["recorded_at"])
                df = df.sort_values("recorded_at")

            return df

        except Exception as e:
            logger.warning(f"Supabase get_recent_readings failed: {e}")
            return pd.DataFrame()