"""Risk management, market hours validation, and position sizing."""

from datetime import datetime
import math
from typing import Optional


class RiskManager:
    """Enforces market trading rules and capital sizing for Indian equities."""

    # Standard NSE Equity trading window (IST)
    MARKET_OPEN_HOUR = 9
    MARKET_OPEN_MINUTE = 15
    MARKET_CLOSE_HOUR = 15
    MARKET_CLOSE_MINUTE = 30

    @classmethod
    def is_market_open(cls, dt: Optional[datetime] = None) -> bool:
        """Check if the current time falls within live NSE equity market hours."""
        now = dt or datetime.now()
        # Monday is 0 and Friday is 4. Saturday (5) and Sunday (6) are closed.
        if now.weekday() >= 5:
            return False

        current_time = now.time()
        market_open = datetime.strptime(f"{cls.MARKET_OPEN_HOUR}:{cls.MARKET_OPEN_MINUTE}", "%H:%M").time()
        market_close = datetime.strptime(f"{cls.MARKET_CLOSE_HOUR}:{cls.MARKET_CLOSE_MINUTE}", "%H:%M").time()

        return market_open <= current_time <= market_close

    @staticmethod
    def calculate_position_size(capital: float, ltp: float, max_quantity: int = 10) -> int:
        """Calculate number of shares based on allocated capital and current price.
        
        Args:
            capital: Allocated INR capital for this trade (e.g. 20,000).
            ltp: Last Traded Price of the stock.
            max_quantity: Safety ceiling for quantity (default: 10).
        """
        if ltp <= 0 or capital <= 0:
            return min(1, max_quantity)

        qty = math.floor(capital / ltp)
        qty = max(1, min(qty, max_quantity))
        return qty

    @staticmethod
    def get_safe_product_type(action: str, preferred_buy_product: str = "INTRADAY") -> str:
        """Enforce exchange-mandated product types.
        
        In Indian cash equities, naked short-selling is only permitted for INTRADAY.
        Delivery (CNC) short sales trigger heavy exchange auction penalties.
        """
        clean_action = action.strip().upper()
        if clean_action in ("SELL", "BEARISH"):
            # Strictly INTRADAY for short selling
            return "INTRADAY"
        return preferred_buy_product.upper()

    @staticmethod
    def parse_exchange_timestamp(dt_str: str) -> Optional[datetime]:
        """Parse diverse date/time formats returned by NSE corporate announcements."""
        if not dt_str:
            return None
        clean = dt_str.strip()
        for fmt in (
            "%d-%b-%Y %H:%M:%S",
            "%d-%m-%Y %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%d-%b-%Y %H:%M",
            "%d-%m-%Y %H:%M",
            "%Y-%m-%dT%H:%M:%S",
        ):
            try:
                return datetime.strptime(clean, fmt)
            except (ValueError, TypeError):
                continue
        return None

    @classmethod
    def is_news_fresh(
        cls,
        an_dt_str: str,
        max_age_seconds: int = 180,
        reference_time: Optional[datetime] = None,
    ) -> tuple[bool, float]:
        """Check if an exchange broadcast timestamp is fresh enough for alpha execution.

        Args:
            an_dt_str: Exchange broadcast timestamp string (e.g. '04-Sep-2026 15:18:43').
            max_age_seconds: Max acceptable age in seconds before news is deemed stale (0 disables check).
            reference_time: Evaluation time (defaults to datetime.now()).

        Returns:
            tuple of (is_fresh: bool, age_seconds: float)
        """
        if max_age_seconds <= 0:
            return True, 0.0

        exchange_time = cls.parse_exchange_timestamp(an_dt_str)
        if not exchange_time:
            # If exchange timestamp cannot be parsed, fail open with 0.0 latency
            return True, 0.0

        ref = reference_time or datetime.now()
        age = (ref - exchange_time).total_seconds()

        # Handle negative delta due to minor clock skew between exchange and local machine
        if age < 0:
            age = 0.0

        is_fresh = age <= max_age_seconds
        return is_fresh, age

    @staticmethod
    def calculate_super_order_levels(
        ltp: float,
        action: str = "BUY",
        target_pct: float = 3.0,
        sl_pct: float = 1.0,
        slippage_buffer_pct: float = 0.2,
    ) -> tuple[float, float, float]:
        """Calculate entry limit, target price, and stop-loss price for a Dhan Super Order.

        Args:
            ltp: Last Traded Price of the security.
            action: 'BUY' or 'SELL'.
            target_pct: Profit target percentage (e.g. 3.0 for 3%).
            sl_pct: Stop-loss percentage (e.g. 1.0 for 1%).
            slippage_buffer_pct: Marketable entry limit buffer percentage (e.g. 0.2 for 0.2%).

        Returns:
            tuple of (entry_limit_price, target_price, stop_loss_price)
        """
        if ltp <= 0:
            return 0.0, 0.0, 0.0

        is_buy = action.upper() in ("BUY", "BULLISH")
        if is_buy:
            # For BUY:
            # Entry limit slightly above LTP (+buffer) to guarantee fill without runaway slippage
            entry_price = round(ltp * (1.0 + slippage_buffer_pct / 100.0), 1)
            target_price = round(ltp * (1.0 + target_pct / 100.0), 1)
            sl_price = round(ltp * (1.0 - sl_pct / 100.0), 1)
        else:
            # For SELL (Short):
            # Entry limit slightly below LTP (-buffer)
            entry_price = round(ltp * (1.0 - slippage_buffer_pct / 100.0), 1)
            target_price = round(ltp * (1.0 - target_pct / 100.0), 1)
            sl_price = round(ltp * (1.0 + sl_pct / 100.0), 1)

        return entry_price, target_price, sl_price


__all__ = ["RiskManager"]


