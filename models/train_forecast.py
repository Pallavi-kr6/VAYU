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
from torch.cuda.amp import GradScaler, autocast
import joblib
from loguru import logger
from tqdm import tqdm
 
from config.settings import FORECAST_CONFIG, MODELS_DIR

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
if torch.cuda.is_available():
    torch.backends.cudnn.benchmark = True
logger.info(f"Device: {DEVICE}")


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
    """Scaled dot-product attention over encoder hidden states."""
    def __init__(self, hidden_size: int):
        super().__init__()
        self.attn  = nn.Linear(hidden_size * 2, hidden_size)
        self.v     = nn.Linear(hidden_size, 1, bias=False)

    def forward(self, encoder_out: torch.Tensor) -> torch.Tensor:
        # encoder_out: [batch, seq_len, hidden*2]
        energy  = torch.tanh(self.attn(encoder_out))  # [B, T, H]
        scores  = self.v(energy).squeeze(-1)           # [B, T]
        weights = torch.softmax(scores, dim=-1)        # [B, T]
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
                target: torch.Tensor = None) -> torch.Tensor:
        """
        x:      [B, seq_len, features]
        target: [B, forecast_len]  (None at inference)
        """
        B = x.size(0)

        # ── Encoder
        enc_out, (h_n, c_n) = self.encoder(x)   # enc_out: [B, T, H*2]
        context, attn_w     = self.attention(enc_out)

        # ── Bridge: avg hidden states of BiLSTM for decoder init
        h_dec = torch.tanh(self.bridge(
            enc_out.mean(dim=1)
        )).unsqueeze(0).repeat(self.decoder.num_layers, 1, 1)
        c_dec = torch.zeros_like(h_dec)

        # ── Decoder (autoregressive)
        # seed with last observed PM2.5 (normalised, first feature idx 0)
        dec_in = x[:, -1, 0:1].unsqueeze(1)   # [B, 1, 1]
        outputs = []

        for t in range(self.forecast_len):
            dec_out, (h_dec, c_dec) = self.decoder(dec_in, (h_dec, c_dec))
            # [B, 1, H] + context [B, H*2]
            combined = torch.cat([dec_out.squeeze(1), context], dim=-1)
            pred     = self.fc(combined)         # [B, 1]
            outputs.append(pred)

            # Teacher forcing during training
            if target is not None and torch.rand(1).item() < teacher_forcing_ratio:
                dec_in = target[:, t:t+1].unsqueeze(-1)
            else:
                dec_in = pred.unsqueeze(1)

        return torch.cat(outputs, dim=1)         # [B, forecast_len]


# ════════════════════════════════════════════════════════
# 3. TRAINING LOOP
# ════════════════════════════════════════════════════════
def train_one_epoch(model, loader, optimizer, criterion, tf_ratio, scaler=None, use_amp=False):
    model.train()
    total_loss = 0
    for X, y in loader:
        X, y = X.to(DEVICE, non_blocking=True), y.to(DEVICE, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)
        with autocast(enabled=use_amp):
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


@torch.no_grad()
def evaluate(model, loader, criterion, use_amp=False):
    model.eval()
    total_loss, preds_all, targets_all = 0, [], []
    for X, y in loader:
        X, y = X.to(DEVICE, non_blocking=True), y.to(DEVICE, non_blocking=True)
        with autocast(enabled=use_amp):
            pred  = model(X, teacher_forcing_ratio=0.0)
            total_loss += criterion(pred, y).item()
        preds_all.append(pred.float().cpu().numpy())
        targets_all.append(y.cpu().numpy())

    preds   = np.concatenate(preds_all).flatten()
    targets = np.concatenate(targets_all).flatten()
    rmse    = np.sqrt(np.mean((preds - targets) ** 2))
    mae     = np.mean(np.abs(preds - targets))
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
    criterion = nn.HuberLoss(delta=15.0)   # robust to extreme pollution spikes
    amp_scaler = GradScaler(enabled=use_amp)

    best_val_rmse = float("inf")
    patience_cnt  = 0
    history       = {"train_loss": [], "val_loss": [], "val_rmse": [], "val_mae": []}

    logger.info("Starting training...")
    for epoch in range(1, cfg["epochs"] + 1):
        # Linear teacher forcing decay: 0.9 → 0.1 over epochs
        tf_ratio = max(0.1, 0.9 - 0.8 * (epoch / cfg["epochs"]))

        train_loss = train_one_epoch(
            model, train_loader, optimizer, criterion, tf_ratio,
            scaler=amp_scaler, use_amp=use_amp,
        )
        val_loss, val_rmse, val_mae = evaluate(
            model, val_loader, criterion, use_amp=use_amp,
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

        checkpoint   = torch.load(model_path, map_location=DEVICE)
        self.features = checkpoint["features"]
        cfg           = checkpoint["config"]

        self.model = VAYUForecastModel(
            input_size   = len(self.features),
            hidden_size  = cfg["hidden_size"],
            num_layers   = cfg["num_layers"],
            dropout      = 0.0,             # no dropout at inference
            forecast_len = cfg["forecast_len"],
        ).to(DEVICE)
        self.model.load_state_dict(checkpoint["model_state"])
        self.model.eval()
        self.scaler = joblib.load("models/saved/aqi_scaler.pkl")
        logger.info(f"ForecastInference loaded (val RMSE={checkpoint['val_rmse']:.2f})")

    @torch.no_grad()
    def predict(self, recent_df: pd.DataFrame, n_steps: int = 192) -> pd.DataFrame:
        """
        recent_df: last 48 rows of AQI + met data (pre-feature-engineered)
        Returns:  DataFrame with columns [step, pm25_pred, aqi_pred, aqi_category]
        """
        import sys
        sys.path.append("..")
        from data.preprocess import engineer_features, compute_aqi

        feat_df   = engineer_features(recent_df)
        feat_cols = [f for f in self.features if f in feat_df.columns]
        X_raw     = feat_df[feat_cols].values[-FORECAST_CONFIG["sequence_len"]:]
        X_scaled  = self.scaler.transform(X_raw)
        X_tensor  = torch.tensor(X_scaled, dtype=torch.float32).unsqueeze(0).to(DEVICE)

        pred      = self.model(X_tensor, teacher_forcing_ratio=0.0)
        pm25_vals = pred.squeeze().cpu().numpy()

        # Inverse-scale PM2.5 (column index 0 in feature list)
        dummy = np.zeros((len(pm25_vals), len(feat_cols)))
        dummy[:, 0] = pm25_vals
        pm25_inv = self.scaler.inverse_transform(dummy)[:, 0]
        pm25_inv = np.maximum(pm25_inv, 0)  # non-negative

        results = []
        for i, pm25 in enumerate(pm25_inv[:n_steps]):
            aqi_val, aqi_cat = compute_aqi(pm25, pm25 * 1.8)  # approximate PM10
            results.append({
                "step_15min":    i + 1,
                "hours_ahead":   round((i + 1) * 0.25, 2),
                "pm25_pred":     round(float(pm25), 1),
                "aqi_pred":      aqi_val,
                "aqi_category":  aqi_cat,
            })
        return pd.DataFrame(results)


if __name__ == "__main__":
    main()
