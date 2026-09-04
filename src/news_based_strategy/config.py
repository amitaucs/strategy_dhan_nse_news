"""Configuration loader and settings management."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Dict

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


# Load environment variables on import
load_env()

DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
}


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    app_env: str = os.getenv("APP_ENV", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Ingestion configuration
    poll_interval_seconds: int = int(os.getenv("NSE_POLL_INTERVAL_SECONDS", "60"))
    nse_base_url: str = os.getenv("NSE_BASE_URL", "https://www.nseindia.com")
    nse_api_url: str = os.getenv(
        "NSE_ANNOUNCEMENTS_API",
        "https://www.nseindia.com/api/corporate-announcements?index=equities",
    )
    headers: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_HEADERS))

    # Pipeline default flags
    fno_only: bool = os.getenv("FNO_ONLY", "true").lower() in ("true", "1", "yes")
    filter_noise: bool = os.getenv("FILTER_NOISE", "true").lower() in ("true", "1", "yes")
    extract_pdf: bool = os.getenv("EXTRACT_PDF", "true").lower() in ("true", "1", "yes")

    # AI Reasoning
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")
    confidence_threshold: int = int(os.getenv("CONFIDENCE_THRESHOLD", "80"))

    # Execution & Risk Parameters
    dhan_client_id: str = os.getenv("DHAN_CLIENT_ID", "")
    dhan_access_token: str = os.getenv("DHAN_ACCESS_TOKEN", "")
    dry_run: bool = os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes")
    capital_per_trade: float = float(os.getenv("CAPITAL_PER_TRADE", "20000.0"))

    # Super Order (Bracket Order with TP, SL, Trailing Jump)
    super_order_enabled: bool = os.getenv("SUPER_ORDER_ENABLED", "true").lower() in ("true", "1", "yes")
    target_profit_pct: float = float(os.getenv("TARGET_PROFIT_PCT", "3.0"))
    stop_loss_pct: float = float(os.getenv("STOP_LOSS_PCT", "1.0"))
    trailing_jump_points: float = float(os.getenv("TRAILING_JUMP_POINTS", "5.0"))
    slippage_buffer_pct: float = float(os.getenv("SLIPPAGE_BUFFER_PCT", "0.2"))

    # Storage & Database (MySQL with SQLite fallback)
    database_path: str = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "strategy.db"))
    mysql_host: str = os.getenv("MYSQL_HOST", "")
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_database: str = os.getenv("MYSQL_DATABASE", "")
    mysql_user: str = os.getenv("MYSQL_USER", "")
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "")

    @property
    def use_mysql(self) -> bool:
        return bool(self.mysql_host and self.mysql_database and self.mysql_user)


settings = Settings()

__all__ = ["Settings", "settings", "DEFAULT_HEADERS", "load_env"]
