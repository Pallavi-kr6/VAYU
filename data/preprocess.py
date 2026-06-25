# data/preprocess.py
# ─────────────────────────────────────────────────────────
# Cleans raw data, engineers all features, and saves
# ready-to-train splits for both models:
#   → forecast_train.parquet / forecast_val.parquet / forecast_test.parquet
#   → attribution_train.parquet / attribution_test.parquet
# ─────────────────────────────────────────────────────────

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.preprocessing import StandardScaler
import joblib

from data.download_data import create_source_attribution_labels, create_synthetic_aqi_data
from config.settings import MODELS_DIR

RAW_DIR       = Path("data/raw")
PROCESSED_DIR = Path("data/processed")
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

from data.aqi_utils import compute_cpcb_aqi as compute_aqi


# ── Feature Engineering ──────────────────────────────────
def _ensure_raw_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise live/synthetic fetch columns to match training pipeline."""
    df = df.copy()
    if "datetime" not in df.columns:
        if "timestamp" in df.columns:
            df["datetime"] = pd.to_datetime(df["timestamp"])
        elif "date" in df.columns:
            df["datetime"] = pd.to_datetime(df["date"])
        else:
            raise KeyError("datetime")
    else:
        df["datetime"] = pd.to_datetime(df["datetime"])

    if "city" not in df.columns:
        df["city"] = "Unknown"

    for col, default in {
        "temp": 25.0, "humidity": 60.0,
        "wind_speed": 3.5, "wind_dir": 180.0, "pblh": 800.0,
    }.items():
        if col not in df.columns:
            df[col] = default

    for p, ratio in {"so2": 0.12, "co": 0.08, "o3": 0.6}.items():
        if p not in df.columns:
            df[p] = df.get("pm25", 50) * ratio

    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds all derived features used by both models.
    Input: raw AQI dataframe with datetime, pollutants, meteorology
    """
    df = _ensure_raw_columns(df)
    df = df.sort_values(["city", "datetime"]).reset_index(drop=True)

    # ── Time features
    df["hour"]         = df["datetime"].dt.hour
    df["day_of_week"]  = df["datetime"].dt.dayofweek
    df["month"]        = df["datetime"].dt.month
    df["day_of_year"]  = df["datetime"].dt.dayofyear
    df["is_weekend"]   = (df["day_of_week"] >= 5).astype(int)

    # Cyclical encoding (so hour 23 is close to hour 0)
    df["hour_sin"]     = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"]     = np.cos(2 * np.pi * df["hour"] / 24)
    df["month_sin"]    = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"]    = np.cos(2 * np.pi * df["month"] / 12)
    df["dow_sin"]      = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["dow_cos"]      = np.cos(2 * np.pi * df["day_of_week"] / 7)

    # ── Wind vector components
    df["wind_u"] = -df["wind_speed"] * np.sin(np.radians(df["wind_dir"]))
    df["wind_v"] = -df["wind_speed"] * np.cos(np.radians(df["wind_dir"]))

    # ── Seasonal event flags
    df["is_diwali_season"] = (
        ((df["month"] == 10) & (df["datetime"].dt.day > 20)) |
        ((df["month"] == 11) & (df["datetime"].dt.day < 5))
    ).astype(int)
    df["is_stubble_season"] = df["month"].isin([10, 11]).astype(int)
    df["is_monsoon"]        = df["month"].isin([6, 7, 8, 9]).astype(int)

    # ── Rush hour flag (morning + evening)
    df["is_rush_hour"] = (
        df["hour"].isin(range(7, 10)) | df["hour"].isin(range(17, 21))
    ).astype(int)

    # ── Rolling stats (per city) — 3h / 6h / 24h windows
    for city, gdf in df.groupby("city"):
        idx = gdf.index
        for col in ["pm25", "pm10", "no2"]:
            df.loc[idx, f"{col}_roll3h"]  = gdf[col].rolling(3,  min_periods=1).mean().values
            df.loc[idx, f"{col}_roll6h"]  = gdf[col].rolling(6,  min_periods=1).mean().values
            df.loc[idx, f"{col}_roll24h"] = gdf[col].rolling(24, min_periods=1).mean().values
            df.loc[idx, f"{col}_lag1h"]   = gdf[col].shift(1).values
            df.loc[idx, f"{col}_lag3h"]   = gdf[col].shift(3).values
            df.loc[idx, f"{col}_lag24h"]  = gdf[col].shift(24).values

    # ── AQI and category
    df[["aqi", "aqi_category"]] = df.apply(
        lambda r: compute_aqi(r["pm25"], r["pm10"]), axis=1, result_type="expand"
    )

    # ── AQI category as integer label for classification
    cat_map = {"Good": 0, "Satisfactory": 1, "Moderate": 2,
               "Poor": 3, "Very Poor": 4, "Severe": 5}
    df["aqi_label"] = df["aqi_category"].map(cat_map)

    # ── Drop NaN rows from rolling / lag
    df = df.dropna(subset=["pm25_lag24h"]).reset_index(drop=True)

    return df


# ── Load or create raw data ──────────────────────────────
def load_raw_data() -> pd.DataFrame:
    kaggle_file = RAW_DIR / "aqi_india_2015_2024" / "city_aqi_hourly.csv"

    if kaggle_file.exists():
        logger.info(f"Loading Kaggle data from {kaggle_file}")
        df = pd.read_csv(kaggle_file)
        # Normalise column names (Kaggle dataset has different casing)
        df.columns = df.columns.str.lower().str.replace(" ", "_")
        # Rename common alternate column names
        rename_map = {
            "date":          "datetime",
            "pm2_5":         "pm25",
            "pm2.5":         "pm25",
            "station":       "city",
            "stationname":   "city",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    else:
        logger.warning("Kaggle data not found — generating synthetic dataset")
        out_dir = RAW_DIR / "aqi_india_2015_2024"
        out_dir.mkdir(exist_ok=True)
        df = create_synthetic_aqi_data(out_dir, "aqi_india_2015_2024")

    # Ensure required columns exist with defaults
    required_meteorology = {
        "temp": 25.0, "humidity": 60.0,
        "wind_speed": 3.5, "wind_dir": 180.0, "pblh": 800.0
    }
    for col, default in required_meteorology.items():
        if col not in df.columns:
            df[col] = default

    for p in ["so2", "co", "o3"]:
        if p not in df.columns:
            df[p] = df.get("pm25", 50) * {"so2": 0.12, "co": 0.08, "o3": 0.6}[p]

    return df


# ── Train / Val / Test Split ─────────────────────────────
def temporal_split(df: pd.DataFrame):
    """
    Temporal split to avoid leakage:
      Train: 2015–2022  (80%)
      Val:   2023       (10%)
      Test:  2024       (10%)
    """
    df["year"] = pd.to_datetime(df["datetime"]).dt.year
    train = df[df["year"] <= 2022].drop(columns=["year"])
    val   = df[df["year"] == 2023].drop(columns=["year"])
    test  = df[df["year"] == 2024].drop(columns=["year"])
    return train, val, test


# ── Feature lists used by each model ─────────────────────
FORECAST_FEATURES = [
    "pm25", "pm10", "no2", "so2", "co", "o3",
    "temp", "humidity", "wind_speed", "wind_u", "wind_v", "pblh",
    "hour_sin", "hour_cos", "month_sin", "month_cos", "dow_sin", "dow_cos",
    "is_weekend", "is_rush_hour", "is_diwali_season",
    "is_stubble_season", "is_monsoon",
    "pm25_roll3h", "pm25_roll6h", "pm25_roll24h",
    "pm25_lag1h", "pm25_lag3h", "pm25_lag24h",
    "pm10_roll6h", "no2_roll6h",
]

ATTRIBUTION_FEATURES = [
    "pm25", "pm10", "no2", "so2", "co", "o3",
    "pm25_roll6h", "pm25_roll24h",
    "no2_roll6h", "pm10_roll6h",
    "wind_u", "wind_v", "wind_speed", "pblh",
    "hour_sin", "hour_cos", "month_sin", "month_cos",
    "is_rush_hour", "is_stubble_season", "is_diwali_season",
    "is_monsoon", "is_weekend",
    "temp", "humidity",
]

ATTRIBUTION_TARGETS = [
    "src_vehicle", "src_construction", "src_industrial",
    "src_biomass", "src_secondary"
]


# ── Main Preprocessing Pipeline ──────────────────────────
def main():
    logger.info("═══ VAYU Preprocessing Pipeline ═══")

    # 1. Load
    logger.info("Step 1/5: Loading raw data...")
    raw = load_raw_data()
    logger.info(f"  Raw shape: {raw.shape}")

    # 2. Feature engineering
    logger.info("Step 2/5: Engineering features...")
    feat = engineer_features(raw)
    logger.info(f"  Feature shape: {feat.shape}, cols: {len(feat.columns)}")

    # 3. Add source attribution labels
    logger.info("Step 3/5: Generating source attribution labels...")
    feat = create_source_attribution_labels(feat)

    # 4. Split
    logger.info("Step 4/5: Temporal train/val/test split...")
    train, val, test = temporal_split(feat)
    logger.info(f"  Train: {len(train):,}  Val: {len(val):,}  Test: {len(test):,}")

    # 5. Scale & save
    logger.info("Step 5/5: Scaling and saving...")
    scaler = StandardScaler()
    train_scaled = train.copy()
    val_scaled   = val.copy()
    test_scaled  = test.copy()

    # Only scale numeric forecast features
    numeric_feats = [f for f in FORECAST_FEATURES if f in train.columns]
    train_scaled[numeric_feats] = scaler.fit_transform(train[numeric_feats])
    val_scaled[numeric_feats]   = scaler.transform(val[numeric_feats])
    test_scaled[numeric_feats]  = scaler.transform(test[numeric_feats])

    # Save scaler for inference
    scaler_path = MODELS_DIR / "aqi_scaler.pkl"
    joblib.dump(scaler, scaler_path)

    # Save splits
    train_scaled.to_parquet(PROCESSED_DIR / "forecast_train.parquet", index=False)
    val_scaled.to_parquet(PROCESSED_DIR   / "forecast_val.parquet",   index=False)
    test_scaled.to_parquet(PROCESSED_DIR  / "forecast_test.parquet",  index=False)

    # Attribution splits (unscaled — tree models don't need scaling)
    train.to_parquet(PROCESSED_DIR / "attribution_train.parquet", index=False)
    test.to_parquet(PROCESSED_DIR  / "attribution_test.parquet",  index=False)

    # Save feature lists
    import json
    json.dump(FORECAST_FEATURES,    open(PROCESSED_DIR / "forecast_features.json", "w"))
    json.dump(ATTRIBUTION_FEATURES, open(PROCESSED_DIR / "attribution_features.json", "w"))
    json.dump(ATTRIBUTION_TARGETS,  open(PROCESSED_DIR / "attribution_targets.json", "w"))

    logger.success("Preprocessing complete!")
    logger.info(f"  Saved to: {PROCESSED_DIR}")


if __name__ == "__main__":
    main()
