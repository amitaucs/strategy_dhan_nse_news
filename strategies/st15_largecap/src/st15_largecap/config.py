"""Configuration settings for ST15_LargeCap Positional Momentum Strategy."""

from dataclasses import dataclass, field
import os
from pathlib import Path


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


@dataclass
class Settings:
    """Configuration loaded from environment variables or .env file."""

    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    # Dhan API / Broker Credentials
    dhan_client_id: str = field(default_factory=lambda: os.getenv("DHAN_CLIENT_ID", ""))
    dhan_access_token: str = field(default_factory=lambda: os.getenv("DHAN_ACCESS_TOKEN", ""))
    dhan_app_id: str = field(default_factory=lambda: os.getenv("DHAN_APP_ID", ""))
    dhan_app_secret: str = field(default_factory=lambda: os.getenv("DHAN_APP_SECRET", ""))
    dhan_redirect_url: str = field(default_factory=lambda: os.getenv("DHAN_REDIRECT_URL", ""))

    # Strategy Parameters
    universe_type: str = field(default_factory=lambda: os.getenv("UNIVERSE_TYPE", "NIFTY_100"))
    max_positions: int = field(default_factory=lambda: int(os.getenv("MAX_POSITIONS", "5")))
    capital_per_position: float = field(default_factory=lambda: float(os.getenv("CAPITAL_PER_POSITION", "50000.0")))
    target_profit_pct: float = field(default_factory=lambda: float(os.getenv("TARGET_PROFIT_PCT", "12.0")))
    stop_loss_pct: float = field(default_factory=lambda: float(os.getenv("STOP_LOSS_PCT", "4.0")))
    trailing_sl_pct: float = field(default_factory=lambda: float(os.getenv("TRAILING_SL_PCT", "3.0")))

    # Execution controls
    dry_run: bool = field(default_factory=lambda: os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes"))
    auto_order: bool = field(default_factory=lambda: os.getenv("AUTO_ORDER", "false").lower() in ("true", "1", "yes"))
    ui_port: int = field(default_factory=lambda: int(os.getenv("PORT", "8015")))


settings = Settings()
