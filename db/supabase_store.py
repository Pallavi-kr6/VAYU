# db/supabase_store.py
# ─────────────────────────────────────────────────────────
# Supabase persistence for VAYU agent outputs & logs.
# Falls back gracefully when SUPABASE_URL / key are unset.
# ─────────────────────────────────────────────────────────

from datetime import datetime
from typing import Any, Optional

from loguru import logger

_client = None


def get_client():
    """Lazy singleton Supabase client (service role for backend writes)."""
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
                "key":        key,
                "data":       value,
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
        """Load entire agent cache into memory on startup."""
        client = get_client()
        if not client:
            return {}
        try:
            resp = (
                client.table(SupabaseStore.CACHE_TABLE)
                .select("key,data,updated_at")
                .execute()
            )
            return {
                row["key"]: {
                    "data":    row["data"],
                    "updated": row["updated_at"],
                }
                for row in (resp.data or [])
            }
        except Exception as e:
            logger.warning(f"Supabase load_all failed: {e}")
            return {}

    @staticmethod
    def get_polluters(city: Optional[str] = None) -> list[dict]:
        client = get_client()
        if not client:
            return []
        try:
            resp = client.table("polluters").select("*").execute()
            return resp.data or []
        except Exception as e:
            logger.warning(f"Supabase polluters read failed: {e}")
            return []

    @staticmethod
    def log_chat(city: str, role: str, message: str, phone: Optional[str] = None) -> None:
        client = get_client()
        if not client:
            return
        try:
            client.table("chat_logs").insert({
                "city":    city,
                "phone":   phone,
                "role":    role,
                "message": message,
            }).execute()
        except Exception as e:
            logger.warning(f"Supabase chat log failed: {e}")

    @staticmethod
    def save_reading(city: str, pm25: float, pm10: float, aqi: int,
                     pollutants: Optional[dict] = None) -> None:
        client = get_client()
        if not client:
            return
        try:
            client.table("city_readings").insert({
                "city":       city,
                "pm25":       pm25,
                "pm10":       pm10,
                "aqi":        aqi,
                "pollutants": pollutants or {},
            }).execute()
        except Exception as e:
            logger.warning(f"Supabase city_readings insert failed: {e}")
