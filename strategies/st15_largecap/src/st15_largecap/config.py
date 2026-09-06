"""Configuration settings for ST15_LargeCap Positional Momentum Strategy."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Dict, List


BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BASE_DIR / ".env"


def load_env(env_path: Path = ENV_FILE) -> None:
    """Minimal built-in .env parser if python-dotenv is not installed."""
    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = val


load_env()


@dataclass(frozen=True)
class Settings:
    """Configuration loaded from environment variables or .env file."""

    app_env: str = os.getenv("APP_ENV", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    host: str = os.getenv("HOST", "0.0.0.0")
    ui_port: int = int(os.getenv("PORT", "8015"))

    # Dhan API / Broker Credentials
    dhan_client_id: str = os.getenv("DHAN_CLIENT_ID", "")
    dhan_access_token: str = os.getenv("DHAN_ACCESS_TOKEN", "")
    dhan_app_id: str = os.getenv("DHAN_APP_ID", "")
    dhan_app_secret: str = os.getenv("DHAN_APP_SECRET", "")
    dhan_redirect_url: str = os.getenv(
        "DHAN_REDIRECT_URL", "http://localhost:8015/api/auth/dhan/callback"
    )
    dhan_auth_url: str = os.getenv("DHAN_AUTH_URL", "https://auth.dhan.co")

    # Strategy Parameters
    universe_type: str = os.getenv("UNIVERSE_TYPE", "NIFTY_200")
    ema_fast: int = int(os.getenv("EMA_FAST", "20"))
    ema_mid: int = int(os.getenv("EMA_MID", "50"))
    ema_slow: int = int(os.getenv("EMA_SLOW", "200"))
    ema_proximity_pct: float = float(os.getenv("EMA_PROXIMITY_PCT", "0.5"))
    supertrend_period: int = int(os.getenv("SUPERTREND_PERIOD", "10"))
    supertrend_multiplier: float = float(os.getenv("SUPERTREND_MULTIPLIER", "3.0"))
    risk_reward_ratio: float = float(os.getenv("RISK_REWARD_RATIO", "3.0"))
    swing_low_lookback: int = int(os.getenv("SWING_LOW_LOOKBACK", "10"))
    history_days: int = int(os.getenv("HISTORY_DAYS", "180"))

    # Position Sizing & Execution Controls
    capital_per_position: float = float(os.getenv("CAPITAL_PER_POSITION", os.getenv("CAPITAL_PER_TRADE", "50000.0")))
    max_positions: int = int(os.getenv("MAX_POSITIONS", "5"))
    product_type: str = os.getenv("PRODUCT_TYPE", "CNC").upper()
    order_type: str = os.getenv("ORDER_TYPE", "FOREVER_OCO").upper()
    dry_run: bool = os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes")
    auto_order: bool = os.getenv("AUTO_ORDER", "false").lower() in ("true", "1", "yes")
    scan_interval_minutes: int = int(os.getenv("SCAN_INTERVAL_MINUTES", "15"))

    # Database
    database_path: str = os.getenv(
        "DATABASE_PATH", str(BASE_DIR / "data" / "st15.db")
    )

    # Upper-case property aliases for compatibility
    @property
    def HOST(self) -> str:
        return self.host

    @property
    def PORT(self) -> int:
        return self.ui_port

    @property
    def DHAN_CLIENT_ID(self) -> str:
        return self.dhan_client_id

    @property
    def DHAN_ACCESS_TOKEN(self) -> str:
        return self.dhan_access_token

    @property
    def DHAN_APP_ID(self) -> str:
        return self.dhan_app_id

    @property
    def DHAN_APP_SECRET(self) -> str:
        return self.dhan_app_secret

    @property
    def UNIVERSE_TYPE(self) -> str:
        return self.universe_type

    @property
    def EMA_FAST(self) -> int:
        return self.ema_fast

    @property
    def EMA_MID(self) -> int:
        return self.ema_mid

    @property
    def EMA_SLOW(self) -> int:
        return self.ema_slow

    @property
    def EMA_PROXIMITY_PCT(self) -> float:
        return self.ema_proximity_pct

    @property
    def SUPERTREND_PERIOD(self) -> int:
        return self.supertrend_period

    @property
    def SUPERTREND_MULTIPLIER(self) -> float:
        return self.supertrend_multiplier

    @property
    def RISK_REWARD_RATIO(self) -> float:
        return self.risk_reward_ratio

    @property
    def SWING_LOW_LOOKBACK(self) -> int:
        return self.swing_low_lookback

    @property
    def HISTORY_DAYS(self) -> int:
        return self.history_days

    @property
    def CAPITAL_PER_TRADE(self) -> float:
        return self.capital_per_position

    @property
    def CAPITAL_PER_POSITION(self) -> float:
        return self.capital_per_position

    @property
    def PRODUCT_TYPE(self) -> str:
        return self.product_type

    @property
    def ORDER_TYPE(self) -> str:
        return self.order_type

    @property
    def DRY_RUN(self) -> bool:
        return self.dry_run

    @property
    def SCAN_INTERVAL_MINUTES(self) -> int:
        return self.scan_interval_minutes

    @property
    def DATABASE_PATH(self) -> str:
        return self.database_path


settings = Settings()

__all__ = ["Settings", "settings", "load_env"]
