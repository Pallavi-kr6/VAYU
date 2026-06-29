# models/train_forecast.py
# ─────────────────────────────────────────────────────────
# Trains a Bidirectional LSTM with Attention for:
#   INPUT:  48-step (12h) lookback of pollutants + met features
#   OUTPUT: 192-step (48h) forecast of PM2.5 / AQI
#
# Architecture: Encoder BiLSTM → Attention → Decoder LSTM
# Loss: Huber (robust to outliers like Diwali spikes)
# ─────────────────────────────────────────────────────────

import sys, json, os
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.amp import GradScaler, autocast
import joblib
from loguru import logger
from tqdm import tqdm
 
from config.settings import FORECAST_CONFIG, MODELS_DIR

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
AMP_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
if torch.cuda.is_available():
    torch.backends.cudnn.benchmark = True
logger.info(f"Device: {DEVICE}")


def _log_tensor_stage(stage: str, tensor: torch.Tensor, *, raise_on_bad: bool = False) -> None:
    """Log tensor shape/statistics and optionally stop at the first NaN/Inf."""
    if tensor is None:
        logger.info(f"---------------------------------------\nStage: {stage}\nShape: None\nNaN count: 0\nInf count: 0\nMin: nan\nMax: nan\nMean: nan\n---------------------------------------")
        return

    arr = tensor.detach().float().cpu()
    flat = arr.reshape(-1)
    nan_count = torch.isnan(flat).sum().item()
    inf_count = torch.isinf(flat).sum().item()

    if flat.numel() == 0:
        mn = mx = mean = float("nan")
    else:
        finite = flat[torch.isfinite(flat)]
        mn = finite.min().item() if finite.numel() else float("nan")
        mx = finite.max().item() if finite.numel() else float("nan")
        mean = finite.mean().item() if finite.numel() else float("nan")

    logger.info(
        f"---------------------------------------\n"
        f"Stage: {stage}\n"
        f"Shape: {tuple(arr.shape)}\n"
        f"NaN count: {nan_count}\n"
        f"Inf count: {inf_count}\n"
        f"Min: {mn:.6f}\n"
        f"Max: {mx:.6f}\n"
        f"Mean: {mean:.6f}\n"
        f"---------------------------------------"
    )

    if raise_on_bad and (nan_count > 0 or inf_count > 0):
        raise RuntimeError(f"NaN/Inf detected at stage: {stage}")


# ════════════════════════════════════════════════════════
# 1. DATASET
# ════════════════════════════════════════════════════════
class AQISequenceDataset(Dataset):
    """
    Creates (lookback_window, forecast_window) pairs per city.
    Each sample:
        X: [seq_len, n_features]   — past weather + pollutants
        y: [forecast_len]          — future PM2.5 values
    """
    def __init__(self, df: pd.DataFrame, features: list[str],
                 seq_len: int = 48, forecast_len: int = 192):
        self.seq_len      = seq_len
        self.forecast_len = forecast_len
        self.samples      = []

        target_col = "pm25"   # Primary forecast target

        for city, gdf in df.groupby("city"):
            gdf = gdf.sort_values("datetime").reset_index(drop=True)
            # Keep only available features
            feat_cols = [f for f in features if f in gdf.columns]
            X_all = gdf[feat_cols].values.astype(np.float32)
            y_all = gdf[target_col].values.astype(np.float32)

            for i in range(seq_len, len(gdf) - forecast_len):
                x = X_all[i - seq_len : i]
                y = y_all[i : i + forecast_len]
                if not (np.isnan(x).any() or np.isnan(y).any()):
                    self.samples.append((x, y))

    def __len__(self): return len(self.samples)

    def __getitem__(self, idx):
        x, y = self.samples[idx]
        return torch.tensor(x), torch.tensor(y)


# ════════════════════════════════════════════════════════
# 2. MODEL — BiLSTM + Temporal Attention + Decoder
# ════════════════════════════════════════════════════════
class TemporalAttention(nn.Module):
    """Decoder cross-attention over encoder hidden states."""
    def __init__(self, hidden_size: int):
        super().__init__()
        # Legacy module retained to preserve compatibility with older checkpoints.
        self.attn = nn.Linear(hidden_size * 2, hidden_size)
        self.query_proj = nn.Linear(hidden_size, hidden_size)
        self.key_proj = nn.Linear(hidden_size * 2, hidden_size)
        self.v = nn.Linear(hidden_size, 1, bias=False)

    def forward(self, encoder_out: torch.Tensor, decoder_hidden: torch.Tensor):
        # encoder_out: [batch, seq_len, hidden*2]
        # decoder_hidden: [batch, hidden]
        query = self.query_proj(decoder_hidden).unsqueeze(1)  # [B, 1, H]
        keys = self.key_proj(encoder_out)  # [B, T, H]
        energy = torch.tanh(query + keys)  # [B, T, H]
        scores = self.v(energy).squeeze(-1)  # [B, T]
        weights = torch.softmax(scores, dim=-1)  # [B, T]
        context = (weights.unsqueeze(-1) * encoder_out).sum(dim=1)  # [B, H*2]
        return context, weights


class VAYUForecastModel(nn.Module):
    """
    Encoder-Decoder LSTM with attention.
        Encoder: BiLSTM processes historical sequence
        Attention: highlights most relevant past timesteps
        Decoder: unrolls to produce 48-hour forecast
    """
    def __init__(self, input_size: int, hidden_size: int = 256,
                 num_layers: int = 3, dropout: float = 0.2,
                 forecast_len: int = 192):
        super().__init__()
        self.forecast_len = forecast_len
        self.hidden_size  = hidden_size

        # Encoder
        self.encoder = nn.LSTM(
            input_size, hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0,
        )
        self.attention = TemporalAttention(hidden_size)

        # Bridge from encoder to decoder (BiLSTM has hidden*2)
        self.bridge = nn.Linear(hidden_size * 2, hidden_size)

        # Decoder
        self.decoder = nn.LSTM(
            1, hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
        )

        # Output head
        self.fc = nn.Sequential(
            nn.Linear(hidden_size + hidden_size * 2, 128),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(128, 1),
        )
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor,
                teacher_forcing_ratio: float = 0.5,
                target: torch.Tensor = None,
                debug: bool = False) -> torch.Tensor:
        """
        x:      [B, seq_len, features]
        target: [B, forecast_len]  (None at inference)
        """
        B = x.size(0)
        teacher_forcing_ratio = float(max(0.0, min(1.0, teacher_forcing_ratio)))

        # ── Encoder
        enc_out, (h_n, c_n) = self.encoder(x)   # enc_out: [B, T, H*2]
        if debug:
            _log_tensor_stage("Encoder outputs", enc_out, raise_on_bad=True)
            _log_tensor_stage("Encoder hidden states", h_n, raise_on_bad=True)
            _log_tensor_stage("Encoder cell states", c_n, raise_on_bad=True)

        # Bridge from the encoder's final forward/backward states.
        h_n = h_n.view(self.encoder.num_layers, 2, B, self.hidden_size)
        h_forward = h_n[-1, 0]
        h_backward = h_n[-1, 1]
        bridge_input = torch.cat([h_forward, h_backward], dim=-1)  # [B, H*2]
        h_dec = torch.tanh(self.bridge(bridge_input)).unsqueeze(0).repeat(
            self.decoder.num_layers, 1, 1
        )
        c_dec = torch.zeros_like(h_dec)
        if debug:
            _log_tensor_stage("Bridge hidden", h_dec, raise_on_bad=True)
            _log_tensor_stage("Bridge cell", c_dec, raise_on_bad=True)

        # ── Decoder (autoregressive)
        # seed with last observed PM2.5 (normalised, first feature idx 0)
        dec_in = x[:, -1, 0:1].unsqueeze(1)  # [B, 1, 1]
        outputs = []

        for t in range(self.forecast_len):
            dec_out, (h_dec, c_dec) = self.decoder(dec_in, (h_dec, c_dec))
            if debug:
                _log_tensor_stage(f"Decoder step {t} output", dec_out, raise_on_bad=True)
            decoder_hidden = h_dec[-1]
            context, weights = self.attention(enc_out, decoder_hidden)
            if debug:
                _log_tensor_stage(f"Attention context step {t}", context, raise_on_bad=True)
                _log_tensor_stage(f"Attention weights step {t}", weights, raise_on_bad=True)
            combined = torch.cat([dec_out.squeeze(1), context], dim=-1)
            if debug:
                _log_tensor_stage(f"Combined step {t}", combined, raise_on_bad=True)
            pred = self.fc(combined)  # [B, 1]
            if debug:
                _log_tensor_stage(f"Output projection step {t}", pred, raise_on_bad=True)
            outputs.append(pred)

            # Teacher forcing during training; inference uses the previous prediction.
            if (
                target is not None
                and self.training
                and torch.rand(1, device=x.device).item() < teacher_forcing_ratio
            ):
                dec_in = target[:, t:t + 1].unsqueeze(-1)
            else:
                dec_in = pred.unsqueeze(1)

        return torch.cat(outputs, dim=1)  # [B, forecast_len]


# ════════════════════════════════════════════════════════
# 3. TRAINING LOOP
# ════════════════════════════════════════════════════════
def train_one_epoch(model, loader, optimizer, criterion, tf_ratio, scaler=None, use_amp=False):
    model.train()
    total_loss = 0
    for X, y in loader:
        X, y = X.to(DEVICE, non_blocking=True), y.to(DEVICE, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)
        with autocast(device_type=AMP_DEVICE, enabled=use_amp):
            pred = model(X, teacher_forcing_ratio=tf_ratio, target=y)
            loss = criterion(pred, y)
        if scaler is not None:
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            scaler.step(optimizer)
            scaler.update()
        else:
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
        total_loss += loss.item()
    return total_loss / len(loader)


def _inverse_pm25(scaled_vals: np.ndarray, scaler, pm25_idx: int) -> np.ndarray:
    """Inverse-transform PM2.5 values from the fitted scaler."""
    scale = scaler.scale_[pm25_idx]
    mean = scaler.mean_[pm25_idx]
    return scaled_vals * scale + mean


@torch.no_grad()
def evaluate(model, loader, criterion, scaler=None, feature_names=None, use_amp=False):
    model.eval()
    total_loss, preds_all, targets_all = 0, [], []
    for X, y in loader:
        X, y = X.to(DEVICE, non_blocking=True), y.to(DEVICE, non_blocking=True)
        with autocast(device_type=AMP_DEVICE, enabled=use_amp):
            pred = model(X, teacher_forcing_ratio=0.0)
            total_loss += criterion(pred, y).item()
        preds_all.append(pred.float().cpu().numpy())
        targets_all.append(y.cpu().numpy())

    preds = np.concatenate(preds_all).flatten()
    targets = np.concatenate(targets_all).flatten()

    if scaler is not None and feature_names is not None:
        pm25_idx = feature_names.index("pm25") if "pm25" in feature_names else 0
        preds = _inverse_pm25(preds, scaler, pm25_idx)
        targets = _inverse_pm25(targets, scaler, pm25_idx)

    rmse = np.sqrt(np.mean((preds - targets) ** 2))
    mae = np.mean(np.abs(preds - targets))
    return total_loss / len(loader), rmse, mae


# ════════════════════════════════════════════════════════
# 4. MAIN TRAINING SCRIPT
# ════════════════════════════════════════════════════════
def main():
    cfg = FORECAST_CONFIG
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("═══ VAYU Forecast Model Training ═══")

    # Load data
    logger.info("Loading processed data...")
    train_df = pd.read_parquet("data/processed/forecast_train.parquet")
    val_df   = pd.read_parquet("data/processed/forecast_val.parquet")
    features = json.load(open("data/processed/forecast_features.json"))
    features = [f for f in features if f in train_df.columns]
    logger.info(f"  Features: {len(features)}  Train rows: {len(train_df):,}")

    # Build datasets
    logger.info("Building sequence datasets...")
    train_ds = AQISequenceDataset(train_df, features,
                                   seq_len=cfg["sequence_len"],
                                   forecast_len=cfg["forecast_len"])
    val_ds   = AQISequenceDataset(val_df,   features,
                                   seq_len=cfg["sequence_len"],
                                   forecast_len=cfg["forecast_len"])
    logger.info(f"  Train samples: {len(train_ds):,}  Val samples: {len(val_ds):,}")

    # Adaptive batch size + DataLoader tuning for ~1-day training on GPU
    batch_size  = cfg["batch_size"] * 2 if torch.cuda.is_available() else cfg["batch_size"]
    num_workers = min(cfg.get("num_workers", 4), os.cpu_count() or 1)
    pin_memory  = torch.cuda.is_available()
    use_amp     = cfg.get("use_amp", True) and torch.cuda.is_available()
    loader_kw   = dict(
        batch_size=batch_size,
        num_workers=num_workers,
        pin_memory=pin_memory,
    )
    if num_workers > 0:
        loader_kw["persistent_workers"] = True
        loader_kw["prefetch_factor"]    = 2

    train_loader = DataLoader(train_ds, shuffle=True,  **loader_kw)
    val_loader   = DataLoader(val_ds,   shuffle=False, **loader_kw)
    logger.info(f"  Batch size: {batch_size}  Workers: {num_workers}  AMP: {use_amp}")

    # Build model
    model = VAYUForecastModel(
        input_size   = len(features),
        hidden_size  = cfg["hidden_size"],
        num_layers   = cfg["num_layers"],
        dropout      = cfg["dropout"],
        forecast_len = cfg["forecast_len"],
    ).to(DEVICE)

    if   (

         cfg.get("compile_model", True) and hasattr(torch, "compile")
         and torch.cuda.is_available()
    ):
              
        try:
            model = torch.compile(model)
            logger.info("  torch.compile enabled")
        except Exception as e:
            logger.warning(f"  torch.compile skipped: {e}")
    else:
        logger.info("  torch.compile disabled")

    total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info(f"Model parameters: {total_params:,}")

    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg["lr"], weight_decay=1e-4)
    scheduler = CosineAnnealingLR(optimizer, T_max=cfg["epochs"], eta_min=1e-5)
    criterion = nn.HuberLoss(delta=1.0)
    amp_scaler = GradScaler(AMP_DEVICE, enabled=use_amp)
    scaler = joblib.load(MODELS_DIR / "aqi_scaler.pkl")

    best_val_rmse = float("inf")
    patience_cnt  = 0
    history       = {"train_loss": [], "val_loss": [], "val_rmse": [], "val_mae": []}

    logger.info("Starting training...")
    for epoch in range(1, cfg["epochs"] + 1):
        tf_ratio = max(0.0, 0.95 - 0.95 * ((epoch - 1) / max(cfg["epochs"] - 1, 1)))

        train_loss = train_one_epoch(
            model, train_loader, optimizer, criterion, tf_ratio,
            scaler=amp_scaler, use_amp=use_amp,
        )
        val_loss, val_rmse, val_mae = evaluate(
            model, val_loader, criterion,
            scaler=scaler, feature_names=features, use_amp=use_amp,
        )
        scheduler.step()

        history["train_loss"].append(float(train_loss))
        history["val_loss"].append(float(val_loss))
        history["val_rmse"].append(float(val_rmse))
        history["val_mae"].append(float(val_mae))

        logger.info(
            f"Epoch {epoch:3d}/{cfg['epochs']} | "
            f"train={train_loss:.4f} | val={val_loss:.4f} | "
            f"RMSE={val_rmse:.2f} µg/m³ | MAE={val_mae:.2f} µg/m³"
        )

        # Save best
        if val_rmse < best_val_rmse:
            best_val_rmse = val_rmse
            patience_cnt  = 0
            torch.save({
                "epoch":      epoch,
                "model_state": model.state_dict(),
                "optimizer":  optimizer.state_dict(),
                "val_rmse":   val_rmse,
                "features":   features,
                "config":     cfg,
            }, MODELS_DIR / "forecast_best.pt")
            logger.success(f"  ✓ New best model saved (RMSE={val_rmse:.2f})")
        else:
            patience_cnt += 1
            if patience_cnt >= cfg["early_stop"]:
                logger.info(f"Early stopping at epoch {epoch}")
                break

     
    json.dump(history, open(MODELS_DIR / "forecast_history.json", "w"), indent=2)
    logger.success(f"Training complete! Best val RMSE: {best_val_rmse:.2f} µg/m³")
    return best_val_rmse


# ════════════════════════════════════════════════════════
# 5. INFERENCE WRAPPER
# ════════════════════════════════════════════════════════
class ForecastInference:
    """
    Loads trained model and produces 48-hour AQI forecast.
    Usage:
        model = ForecastInference()
        forecast = model.predict(recent_df)   # last 12h of readings
    """
    def __init__(self, model_path: str = None):
        if model_path is None:
            model_path = str(MODELS_DIR / "forecast_best.pt")

        checkpoint   = torch.load(model_path, map_location=DEVICE,
    weights_only=False
)
        self.features = checkpoint["features"]
        cfg           = checkpoint["config"]

        self.model = VAYUForecastModel(
            input_size   = len(self.features),
            hidden_size  = cfg["hidden_size"],
            num_layers   = cfg["num_layers"],
            dropout      = 0.0,             # no dropout at inference
            forecast_len = cfg["forecast_len"],
        ).to(DEVICE)
        self.model.load_state_dict(checkpoint["model_state"], strict=False)
        self.model.eval()
        self.scaler = joblib.load(MODELS_DIR / "aqi_scaler.pkl")
        self.pm25_idx = self.features.index("pm25") if "pm25" in self.features else 0
        logger.info(f"ForecastInference loaded (val RMSE={checkpoint['val_rmse']:.2f} scaled units)")

    def _inverse_pm25(self, scaled_vals: np.ndarray) -> np.ndarray:
        """Inverse-transform PM2.5 from scaler (single feature column)."""
        scale = self.scaler.scale_[self.pm25_idx]
        mean  = self.scaler.mean_[self.pm25_idx]
        return scaled_vals * scale + mean

    @torch.no_grad()
    def predict(self, recent_df: pd.DataFrame, n_steps: int = 192) -> pd.DataFrame:
        """
        recent_df: last 48 rows of AQI + met data (pre-feature-engineered)
        Returns DataFrame with pm25_pred, aqi_pred, aqi_category
        """
        from data.preprocess import engineer_features
        from data.aqi_utils import waqi_aqi_category, scale_aqi_from_pm25

        recent_df = recent_df.copy()
        
        # Fill missing meteorological data with forward fill (smooth variations)
        # Then interpolate remaining small gaps
        met_cols = ["temp", "humidity", "wind_speed", "wind_dir", "pressure", "rainfall_mm", "pblh"]
        poll_cols = ["pm25", "pm10", "no2", "so2", "co", "o3"]
        
        for col in met_cols:
            if col in recent_df.columns:
                recent_df[col] = recent_df[col].ffill().bfill().interpolate(method="linear", limit_direction="both")
        
        for col in poll_cols:
            if col in recent_df.columns:
                recent_df[col] = recent_df[col].ffill().bfill().interpolate(method="linear", limit_direction="both")
        
        # After filling, ensure we have pm25 (the critical feature)
        if "pm25" not in recent_df.columns or recent_df["pm25"].isna().all():
            raise ValueError("PM2.5 data is required for forecast but all values are NaN.")
        
        # Drop only rows where critical columns (pm25) are still NaN
        recent_df = recent_df.dropna(subset=["pm25"]).copy()
        if recent_df.empty:
            raise ValueError("No rows with valid PM2.5 data available for forecast.")

        feat_df = engineer_features(recent_df)
        feat_cols = [f for f in self.features if f in feat_df.columns]
        seq_len = FORECAST_CONFIG["sequence_len"]

        # If we don't have enough rows after cleaning, pad with repeated recent values
        if len(feat_df) < seq_len:
            logger.warning(f"Only {len(feat_df)} rows available, need {seq_len}. Padding with repeated recent values.")
            # Repeat the most recent row to reach seq_len
            last_row = feat_df.iloc[-1:].copy()
            padding = pd.concat([last_row] * (seq_len - len(feat_df)), ignore_index=True)
            feat_df = pd.concat([feat_df, padding], ignore_index=True)

        X_df = feat_df[feat_cols].tail(seq_len).copy()
        if len(X_df) < seq_len:
            raise ValueError(f"Failed to prepare enough rows for forecast; got {len(X_df)}/{seq_len}")

        current_pm25 = float(recent_df["pm25"].iloc[-1])
        current_pm10 = float(
            recent_df["pm10"].iloc[-1] if "pm10" in recent_df.columns
            else current_pm25 * 1.8
        )
        if "aqi" in recent_df.columns:
            live_aqi = int(recent_df["aqi"].iloc[-1])
        else:
            from data.aqi_utils import us_aqi_from_pm25
            live_aqi = us_aqi_from_pm25(current_pm25)
        pm10_ratio = current_pm10 / max(current_pm25, 1.0)

        if not np.isfinite(X_df[feat_cols].to_numpy()).all():
            bad_cols = X_df[feat_cols].columns[np.isnan(X_df[feat_cols].to_numpy()).any(axis=0)].tolist()
            raise ValueError(f"NaN/Inf values detected in engineered features before scaling: {bad_cols}")

        X_scaled = self.scaler.transform(X_df)
        _log_tensor_stage("Scaled features", torch.tensor(X_scaled, dtype=torch.float32), raise_on_bad=False)
        X_tensor = torch.tensor(X_scaled, dtype=torch.float32).unsqueeze(0).to(DEVICE)
        _log_tensor_stage("Model input tensor", X_tensor, raise_on_bad=False)

        pred_raw = self.model(X_tensor, teacher_forcing_ratio=0.0, debug=True)
        pm25_scaled = pred_raw.squeeze().cpu().numpy()

        logger.info("=" * 60)
        logger.info("RAW MODEL OUTPUT DEBUG")
        logger.info("=" * 60)
        logger.info(f"pred_raw shape: {tuple(pred_raw.shape)}")
        logger.info(f"pm25_scaled shape: {pm25_scaled.shape}")
        logger.info(f"First 20 scaled predictions: {pm25_scaled[:20]}")
        logger.info(f"Last 20 scaled predictions: {pm25_scaled[-20:]}")
        logger.info(f"Min prediction: {np.min(pm25_scaled):.6f}")
        logger.info(f"Max prediction: {np.max(pm25_scaled):.6f}")
        logger.info(f"Mean prediction: {np.mean(pm25_scaled):.6f}")
        logger.info(f"Std prediction: {np.std(pm25_scaled):.6f}")
        logger.info(f"Unique values (4 dp): {len(np.unique(np.round(pm25_scaled, 4)))}")
        logger.info(f"Contains NaN: {np.isnan(pm25_scaled).any()}")
        logger.info(f"Contains Inf: {np.isinf(pm25_scaled).any()}")
        logger.info(f"All predictions identical: {np.allclose(pm25_scaled, pm25_scaled[0])}")
        if np.allclose(pm25_scaled, pm25_scaled[0]):
            logger.warning("Decoder appears to have collapsed to a constant prediction.")
        logger.info("=" * 60)

        logger.info(f"Raw forecast (scaled): {pm25_scaled[:10].round(3).tolist()}")

        # Clip to training distribution (±2.5σ in scaled space)
        pm25_scaled = np.clip(pm25_scaled, -2.5, 2.5)
        pm25_inv = self._inverse_pm25(pm25_scaled)
        
        if np.isnan(pm25_inv).any():
            raise ValueError("Model produced NaN values after inverse scaling.")

        logger.info(f"Inverse forecast PM2.5 µg/m³: {pm25_inv[:10].round(1).tolist()}")

        # Ramp model trust over first 12h to anchor to current live reading
        n = min(n_steps, len(pm25_inv))
        for i in range(n):
            alpha = min(1.0, i / 48.0)
            pm25_inv[i] = (1.0 - alpha) * current_pm25 + alpha * pm25_inv[i]

        # Physical bounds anchored to current live reading
        upper = min(
            max(current_pm25 * 2.5 + 20.0, current_pm25 + 15.0),
            350.0,
        )
        lower = max(0.0, current_pm25 * 0.4)
        pm25_inv = np.clip(pm25_inv[:n], lower, upper)

        results = []
        for i, pm25 in enumerate(pm25_inv):
            pm10 = pm25 * pm10_ratio
            aqi_val = scale_aqi_from_pm25(live_aqi, current_pm25, pm25)
            aqi_cat = waqi_aqi_category(aqi_val)
            results.append({
                "step_15min":    i + 1,
                "hours_ahead":   round((i + 1) * 0.25, 2),
                "pm25_pred":     round(float(pm25), 1),
                "pm10_pred":     round(float(pm10), 1),
                "aqi_pred":      aqi_val,
                "aqi_category":  aqi_cat,
            })

        aqi_vals = [r["aqi_pred"] for r in results[:10]]
        logger.info(f"AQI forecast (WAQI-scaled): {aqi_vals}")

        return pd.DataFrame(results)


if __name__ == "__main__":
    main()
