"""ST-14 Bullish CE Options Trading Strategy Execution Engine."""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, time as dtime
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from scanner_dhan.data.dhan_provider import DhanDataProvider
from scanner_dhan.scanner.st14_scanner import BullishCeIntradayScanner, St14Status
from st14_bullish_ce.breadth import check_market_breadth
from st14_bullish_ce.models import (
    BreakoutWatchlistItem,
    ExecutionMode,
    OrderStatus,
    ProductType,
    St14OptionContract,
    St14Position,
    St14StrategyConfig,
    St14SuperOrderLevels,
    St14TradeSignal,
)
from st14_bullish_ce.options import resolve_1otm_ce_contract
from st14_bullish_ce.trigger import check_breakout_candle_cross

logger = logging.getLogger(__name__)

__all__ = ["St14BullishCeStrategy"]


class St14BullishCeStrategy:
    """End-to-end execution orchestrator for ST-14 Bullish CE Options Strategy."""

    def __init__(
        self,
        config: Optional[St14StrategyConfig] = None,
        provider: Optional[DhanDataProvider] = None,
    ) -> None:
        self.config = config or St14StrategyConfig()
        self.provider = provider or DhanDataProvider()
        self.scanner = BullishCeIntradayScanner()
        self.active_positions: Dict[str, St14Position] = {}
        self.closed_positions: List[St14Position] = []
        self.signals_history: List[St14TradeSignal] = []
        self.breakout_watchlist: Dict[str, BreakoutWatchlistItem] = {}
        self.last_hourly_scan_time: Optional[str] = None
        self.last_5min_check_time: Optional[str] = None
        self.last_hourly_candidates_count: int = 0
        self._lock = threading.Lock()
        self._executed_signal_ids: set[str] = set()
        self._executed_order_keys: set[str] = set()
        self._journal_file = os.path.join(getattr(self.config, "data_dir", "data"), "st14_executed_orders.json")
        self._load_executed_journal()
        self._last_breadth_status: Dict[str, Any] = {}
        try:
            _, self._last_breadth_status = check_market_breadth(provider=self.provider)
        except Exception:
            self._last_breadth_status = {}

    def _load_executed_journal(self) -> None:
        """Load executed order idempotency keys from disk for today to survive process restarts."""
        try:
            if os.path.exists(self._journal_file):
                with open(self._journal_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                today_str = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
                for item in data.get("executed_orders", []):
                    if item.get("date") == today_str:
                        if "key" in item:
                            self._executed_order_keys.add(item["key"])
                        if "signal_id" in item:
                            self._executed_signal_ids.add(item["signal_id"])
        except Exception as e:
            logger.warning("Could not load ST14 executed orders journal from %s: %s", self._journal_file, e)

    def _persist_executed_order(self, key: str, signal_id: str, order_id: str, symbol: str) -> None:
        """Durable append of executed order to disk journal."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self._journal_file)), exist_ok=True)
            today_str = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
            data: Dict[str, Any] = {"executed_orders": []}
            if os.path.exists(self._journal_file):
                try:
                    with open(self._journal_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {"executed_orders": []}

            data.setdefault("executed_orders", []).append({
                "date": today_str,
                "timestamp": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
                "key": key,
                "signal_id": signal_id,
                "order_id": order_id,
                "symbol": symbol,
            })
            with open(self._journal_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to persist ST14 executed order to journal %s: %s", self._journal_file, e)

    def is_within_entry_window(self, target_dt: Optional[datetime] = None) -> Tuple[bool, str]:
        """Verify if current execution time is between 10:15 AM and 14:00 PM (2:00 PM) IST."""
        ist = ZoneInfo("Asia/Kolkata")
        now = (target_dt or datetime.now(ist)).astimezone(ist)
        cur_min = now.hour * 60 + now.minute

        start_min = 10 * 60 + 15  # 10:15 AM
        try:
            ch, cm = map(int, self.config.trade_cutoff_time.split(":"))
            cutoff_min = ch * 60 + cm
        except Exception:
            cutoff_min = 14 * 60  # 14:00 (2:00 PM) default

        if cur_min < start_min:
            return False, f"Early session before 10:15 AM IST (Entry opens at 10:15)"
        if cur_min >= cutoff_min:
            return False, f"Trade cutoff reached after {self.config.trade_cutoff_time} IST (No new positions)"
        return True, f"Active entry window (10:15 - {self.config.trade_cutoff_time} IST)"

    def is_square_off_time(self, target_dt: Optional[datetime] = None) -> bool:
        """Check if 15:00 (3:00 PM IST) intraday auto square-off time is reached."""
        if self.config.product_type != ProductType.INTRADAY:
            return False
        ist = ZoneInfo("Asia/Kolkata")
        now = (target_dt or datetime.now(ist)).astimezone(ist)
        try:
            sh, sm = map(int, self.config.square_off_time.split(":"))
            sq_min = sh * 60 + sm
        except Exception:
            sq_min = 15 * 60  # 15:00 default
        cur_min = now.hour * 60 + now.minute
        return cur_min >= sq_min

    def calculate_super_order_levels(self, option_ltp: float) -> St14SuperOrderLevels:
        """Calculate Entry limit, Target Profit leg, and Stop Loss leg."""
        entry = round(option_ltp * (1.0 + self.config.slippage_buffer_pct / 100.0), 2)
        target = round(entry * (1.0 + self.config.target_profit_pct / 100.0), 2)
        sl = round(entry * (1.0 - self.config.stop_loss_pct / 100.0), 2)

        return St14SuperOrderLevels(
            entry_price=entry,
            target_price=target,
            stop_loss_price=sl,
            target_pct=self.config.target_profit_pct,
            stop_loss_pct=self.config.stop_loss_pct,
            trailing_jump=self.config.trailing_jump_pts,
        )

    def calculate_order_quantity(self, option_entry_price: float, lot_size: int = 250) -> int:
        """Calculate position sizing strictly bounded by allocated capital per trade.
        
        Returns 0 if the cost of a single lot exceeds the allocated capital per trade,
        preventing oversized positions from being placed.
        """
        cost_per_lot = option_entry_price * lot_size
        if cost_per_lot <= 0:
            return 0
        num_lots = int(self.config.capital_per_trade / cost_per_lot)
        return num_lots * lot_size

    def run_hourly_discovery_scan(
        self,
        target_dt: Optional[datetime] = None,
        bypass_timing: bool = False,
    ) -> Dict[str, Any]:
        """Run Tier 1: 1-Hour Discovery Scanner across 228 F&O stocks to identify new breakout setups."""
        if not self.config.enabled or self.config.status != "ACTIVE":
            return {
                "status": "PAUSED",
                "message": "Strategy Engine is PAUSED. Discovery scan suspended.",
                "discovered_count": 0,
                "watchlist_count": len(self.breakout_watchlist),
                "candidates": [item.to_dict() for item in self.breakout_watchlist.values()],
                "breadth": self._last_breadth_status,
            }

        ist = ZoneInfo("Asia/Kolkata")
        now_dt = (target_dt or datetime.now(ist)).astimezone(ist)
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        # 1. Timing Gate Check (10:15 - 14:00 IST)
        if not bypass_timing:
            is_window_valid, timing_msg = self.is_within_entry_window(target_dt)
            if not is_window_valid:
                logger.info("⏳ [ST-14 Discovery Scan] %s", timing_msg)
                return {
                    "status": "STANDBY",
                    "message": timing_msg,
                    "discovered_count": 0,
                    "watchlist_count": len(self.breakout_watchlist),
                    "candidates": [item.to_dict() for item in self.breakout_watchlist.values()],
                    "breadth": self._last_breadth_status,
                }

        # 2. Check Macro Breadth Gate
        is_breadth_green, breadth_info = check_market_breadth(provider=self.provider)
        self._last_breadth_status = breadth_info
        if not is_breadth_green:
            logger.info("⏸️ [ST-14 Discovery Scan] Market Breadth Gate Blocked: %s", breadth_info.get("message"))
            return {
                "status": "BREADTH_BLOCKED",
                "message": breadth_info.get("message", "Nifty & Bank Nifty not green"),
                "discovered_count": 0,
                "watchlist_count": len(self.breakout_watchlist),
                "candidates": [item.to_dict() for item in self.breakout_watchlist.values()],
                "breadth": breadth_info,
            }

        # 3. Candidate Discovery via ST-14 Scanner
        scan_report = self.scanner.run(
            params={
                "universe": self.config.universe,
                "vwap_min_dist_pct": self.config.vwap_min_dist_pct,
                "vwap_max_dist_pct": self.config.vwap_max_dist_pct,
                "require_rising_vwap": self.config.require_rising_vwap,
                "enforce_timing": not bypass_timing,
            },
            provider=self.provider,
        )

        qualified_results = [r for r in scan_report.results if r.status == St14Status.QUALIFIED]
        logger.info(
            "🔍 [ST-14 Discovery Scan] Qualified Candidates: %d of %d",
            len(qualified_results),
            scan_report.total_scanned,
        )

        today_date = now_dt.date()
        for cand in qualified_results:
            breakout_high = cand.five_hour_high
            current_ltp = cand.ltp
            distance_pct = round(((current_ltp - breakout_high) / breakout_high) * 100.0, 2) if breakout_high > 0 else 0.0

            opt_contract = resolve_1otm_ce_contract(
                symbol=cand.symbol,
                underlying_ltp=current_ltp,
                provider=self.provider,
                current_date=today_date,
            )
            if not opt_contract:
                logger.warning("⛔ [ST-14 Discovery] Excluded %s: No active F&O derivatives on Dhan.", cand.symbol)
                continue

            levels = self.calculate_super_order_levels(option_ltp=opt_contract.ltp)

            existing = self.breakout_watchlist.get(cand.symbol)
            curr_status = existing.status if existing else OrderStatus.WAITING_TRIGGER

            item = BreakoutWatchlistItem(
                symbol=cand.symbol,
                security_id=cand.security_id,
                breakout_candle_high=breakout_high,
                current_ltp=current_ltp,
                distance_pct=distance_pct,
                daily_ema20=cand.daily_ema20,
                hourly_ema20=cand.hourly_ema20,
                vwap=cand.vwap,
                status=curr_status,
                option_contract=opt_contract,
                order_levels=levels,
                discovered_at_ist=existing.discovered_at_ist if existing else now_str,
                last_checked_at_ist=now_str,
                remarks=f"Discovered by 1H Scanner. Breakout High: ₹{breakout_high:.2f}",
            )
            self.breakout_watchlist[cand.symbol] = item

        self.last_hourly_scan_time = now_str
        self.last_hourly_candidates_count = len(qualified_results)

        return {
            "status": "COMPLETED",
            "discovered_count": len(qualified_results),
            "watchlist_count": len(self.breakout_watchlist),
            "candidates": [item.to_dict() for item in self.breakout_watchlist.values()],
            "breadth": self._last_breadth_status,
        }

    def run_5min_trigger_monitor(
        self,
        target_dt: Optional[datetime] = None,
        bypass_timing: bool = False,
    ) -> Dict[str, Any]:
        """Run Tier 2: 5-Minute Trigger Poller to check if Breakout Candle High is breached."""
        if not self.config.enabled or self.config.status != "ACTIVE":
            return {
                "status": "PAUSED",
                "message": "Strategy Engine is PAUSED. Trigger monitor suspended.",
                "triggered_count": 0,
                "orders_placed": 0,
                "watchlist": [item.to_dict() for item in self.breakout_watchlist.values()],
            }

        ist = ZoneInfo("Asia/Kolkata")
        now_dt = (target_dt or datetime.now(ist)).astimezone(ist)
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        # 1. Timing Gate Check
        if not bypass_timing:
            is_window_valid, timing_msg = self.is_within_entry_window(target_dt)
            if not is_window_valid:
                return {
                    "status": "STANDBY",
                    "message": timing_msg,
                    "triggered_count": 0,
                    "orders_placed": 0,
                    "watchlist": [item.to_dict() for item in self.breakout_watchlist.values()],
                }

        today_date = now_dt.date()
        triggered_signals: List[St14TradeSignal] = []
        orders_placed = 0
        executed_positions: List[Dict[str, Any]] = []

        for symbol, item in list(self.breakout_watchlist.items()):
            if item.status != OrderStatus.WAITING_TRIGGER:
                continue

            if len(self.active_positions) >= self.config.max_open_positions:
                logger.warning("⚠️ Max open positions limit reached (%d).", self.config.max_open_positions)
                break

            is_crossed, live_ltp, cross_msg = check_breakout_candle_cross(
                symbol=item.symbol,
                sec_id=item.security_id,
                breakout_candle_high=item.breakout_candle_high,
                current_ltp=item.current_ltp,
                provider=self.provider,
            )

            item.current_ltp = live_ltp
            item.last_checked_at_ist = now_str
            if item.breakout_candle_high > 0:
                item.distance_pct = round(((live_ltp - item.breakout_candle_high) / item.breakout_candle_high) * 100.0, 2)

            if is_crossed:
                logger.info("🚀 [ST-14 Trigger Hit] %s: Live LTP ₹%.2f crossed Breakout High ₹%.2f!", symbol, live_ltp, item.breakout_candle_high)

                opt_contract = resolve_1otm_ce_contract(
                    symbol=symbol,
                    underlying_ltp=live_ltp,
                    provider=self.provider,
                    current_date=today_date,
                )
                if not opt_contract:
                    logger.warning("⛔ [ST-14 Trigger] Excluded %s: No active F&O option contract found.", symbol)
                    item.status = OrderStatus.DISQUALIFIED
                    item.remarks = "Disqualified: Not an active F&O option on Dhan"
                    continue

                levels = self.calculate_super_order_levels(option_ltp=opt_contract.ltp)
                item.option_contract = opt_contract
                # Real-time Market Breadth re-validation before trigger order
                is_breadth_green, breadth_info = check_market_breadth(provider=self.provider)
                self._last_breadth_status = breadth_info
                nifty_green = bool(breadth_info.get("nifty50_green", False))
                banknifty_green = bool(breadth_info.get("banknifty_green", False))

                if not is_breadth_green:
                    breadth_msg = breadth_info.get("message", "Market breadth not green")
                    logger.warning("⛔ [ST-14 Trigger] %s breached but breadth gate failed: %s", symbol, breadth_msg)
                    item.remarks = f"Trigger hit but breadth blocked: {breadth_msg}"
                    continue

                signal = St14TradeSignal(
                    signal_id=f"ST14_{symbol}_{int(now_dt.timestamp())}",
                    symbol=symbol,
                    underlying_sec_id=item.security_id,
                    underlying_ltp=live_ltp,
                    breakout_candle_high=item.breakout_candle_high,
                    daily_ema20=item.daily_ema20,
                    hourly_ema20=item.hourly_ema20,
                    vwap=item.vwap,
                    vwap_dist_pct=0.0,
                    vwap_angle_deg=45.0,
                    status=OrderStatus.TRIGGERED,
                    nifty_green=nifty_green,
                    banknifty_green=banknifty_green,
                    is_confirmed=True,
                    option_contract=opt_contract,
                    order_levels=levels,
                    remarks=cross_msg,
                )
                triggered_signals.append(signal)
                self.signals_history.append(signal)

                if self.config.auto_order:
                    success, remarks, pos = self.execute_order(signal)
                    if success and pos:
                        orders_placed += 1
                        executed_positions.append(pos.to_dict())
                        item.status = OrderStatus.ORDER_PLACED
                        item.order_id = pos.position_id
                        item.remarks = remarks
                    else:
                        item.status = OrderStatus.ORDER_REJECTED
                        item.remarks = remarks
                else:
                    item.status = OrderStatus.TRIGGERED
                    item.remarks = f"⚡ Trigger Confirmed! Ready for 1-Click Execution ({self.config.mode.value} Mode)"
            else:
                item.remarks = cross_msg

        self.last_5min_check_time = now_str

        return {
            "status": "COMPLETED",
            "checked_count": len([i for i in self.breakout_watchlist.values() if i.status == OrderStatus.WAITING_TRIGGER]),
            "triggered_count": len(triggered_signals),
            "orders_placed": orders_placed,
            "executed_positions": executed_positions,
            "watchlist": [item.to_dict() for item in self.breakout_watchlist.values()],
        }

    def evaluate_market_and_scan(
        self,
        target_dt: Optional[datetime] = None,
        bypass_timing: bool = False,
    ) -> List[St14TradeSignal]:
        """Runs full discovery scan followed by trigger check and returns all active trade signals."""
        self.run_hourly_discovery_scan(target_dt=target_dt, bypass_timing=bypass_timing)
        res = self.run_5min_trigger_monitor(target_dt=target_dt, bypass_timing=bypass_timing)
        return list(self.signals_history[-15:])

    def execute_order(self, signal: St14TradeSignal) -> Tuple[bool, str, Optional[St14Position]]:
        """Dispatch Super Order on DhanHQ or Virtual Paper Trading Engine."""
        with self._lock:
            if not signal.is_confirmed or not signal.option_contract or not signal.order_levels:
                return False, "Signal not confirmed for execution", None

            if signal.status == OrderStatus.ORDER_PLACED or (signal.order_id and signal.order_id.strip()):
                return False, f"Order already placed for signal {signal.signal_id} (Order ID: {signal.order_id})", None

            if signal.signal_id in self._executed_signal_ids:
                return False, f"Signal {signal.signal_id} has already been executed.", None

            opt = signal.option_contract
            today_str = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
            idempotency_key = f"{opt.underlying_symbol}_{opt.security_id}_{today_str}"

            # Broker-level / active position duplicate prevention
            for pos in self.active_positions.values():
                if pos.symbol == opt.underlying_symbol or pos.security_id == opt.security_id:
                    return False, f"Active position already open for {opt.underlying_symbol} ({pos.position_id})", None

            if idempotency_key in self._executed_order_keys:
                return False, f"Order key {idempotency_key} has already been submitted today.", None

            levels = signal.order_levels
            qty = self.calculate_order_quantity(
                option_entry_price=levels.entry_price,
                lot_size=opt.lot_size,
            )

            if qty <= 0:
                cost_1lot = levels.entry_price * opt.lot_size
                remarks = (
                    f"❌ [ORDER REJECTED] {opt.symbol}: Cost of 1 lot (₹{cost_1lot:,.2f}) "
                    f"exceeds allocated capital per trade (₹{self.config.capital_per_trade:,.2f})."
                )
                logger.warning(remarks)
                signal.status = OrderStatus.ORDER_REJECTED
                signal.remarks = remarks
                return False, remarks, None

            now_ist_str = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")

            # 1. Virtual Paper Trading Mode
            if self.config.mode == ExecutionMode.VIRTUAL or not self.provider.dhan:
                sim_order_id = f"SIM_SUPER_{opt.underlying_symbol}_{int(opt.strike_price)}_{uuid.uuid4().hex[:6].upper()}"
                remarks = (
                    f"🛡️ [VIRTUAL SUPER ORDER] Bought {qty} qty {opt.symbol} @ ₹{levels.entry_price:.2f} "
                    f"(Target: ₹{levels.target_price:.2f} [+40%], SL: ₹{levels.stop_loss_price:.2f} [-20%], Trail: {levels.trailing_jump} pts)"
                )
                logger.info(remarks)

                position = St14Position(
                    position_id=sim_order_id,
                    symbol=opt.underlying_symbol,
                    option_symbol=opt.symbol,
                    security_id=opt.security_id,
                    quantity=qty,
                    entry_price=levels.entry_price,
                    current_ltp=levels.entry_price,
                    target_price=levels.target_price,
                    stop_loss_price=levels.stop_loss_price,
                    product_type=self.config.product_type,
                    mode=ExecutionMode.VIRTUAL,
                    entry_time_ist=now_ist_str,
                )
                self.active_positions[sim_order_id] = position
                self._executed_signal_ids.add(signal.signal_id)
                self._executed_order_keys.add(idempotency_key)
                self._persist_executed_order(idempotency_key, signal.signal_id, sim_order_id, opt.underlying_symbol)
                signal.status = OrderStatus.ORDER_PLACED
                signal.order_id = sim_order_id
                return True, remarks, position

            # 2. Live Execution Mode via DhanHQ Super Order API
            try:
                if opt.is_synthetic:
                    remarks = f"❌ [LIVE ORDER REJECTED] {opt.symbol}: Option contract is synthetic / unverified from live exchange option chain."
                    logger.error(remarks)
                    signal.status = OrderStatus.ORDER_REJECTED
                    signal.remarks = remarks
                    return False, remarks, None

                if not opt.security_id or not opt.security_id.isdigit():
                    remarks = f"❌ [LIVE ORDER REJECTED] {opt.symbol}: Invalid non-numeric security ID '{opt.security_id}' for live broker execution."
                    logger.error(remarks)
                    signal.status = OrderStatus.ORDER_REJECTED
                    signal.remarks = remarks
                    return False, remarks, None

                dhan = self.provider.dhan
                dhan_prod = dhan.INTRA if self.config.product_type == ProductType.INTRADAY else dhan.MARGIN

                # Broker margin check immediately before live placement (Strict fail-closed)
                try:
                    # 1. Query exact required margin from Dhan margin_calculator API
                    if hasattr(dhan, "margin_calculator"):
                        margin_resp = dhan.margin_calculator(
                            security_id=str(opt.security_id),
                            exchange_segment=dhan.NSE_FNO,
                            transaction_type=dhan.BUY,
                            quantity=qty,
                            product_type=dhan_prod,
                            price=levels.entry_price,
                        )
                    else:
                        margin_resp = None

                    if not (isinstance(margin_resp, dict) and margin_resp.get("status") == "success"):
                        err_msg = margin_resp.get("remarks", margin_resp) if isinstance(margin_resp, dict) else "Margin calculator unavailable"
                        remarks = f"❌ [LIVE ORDER REJECTED] {opt.symbol}: Broker margin calculation failed ({err_msg})."
                        logger.error(remarks)
                        signal.status = OrderStatus.ORDER_REJECTED
                        signal.remarks = remarks
                        return False, remarks, None

                    margin_data = margin_resp.get("data", {})
                    required_margin = float(
                        margin_data.get("totalMargin")
                        or margin_data.get("marginRequirement")
                        or (levels.entry_price * qty)
                    )
                    if required_margin <= 0:
                        required_margin = levels.entry_price * qty

                    # 2. Query live available funds from Dhan fund limits API
                    fund_resp = (
                        self.provider.fetch_fund_limits()
                        if hasattr(self.provider, "fetch_fund_limits")
                        else (dhan.get_fund_limits() if hasattr(dhan, "get_fund_limits") else None)
                    )
                    if not (isinstance(fund_resp, dict) and fund_resp.get("status") == "success"):
                        err_msg = fund_resp.get("remarks", fund_resp) if isinstance(fund_resp, dict) else "Fund limits unavailable"
                        remarks = f"❌ [LIVE ORDER REJECTED] {opt.symbol}: Broker fund limit check failed ({err_msg})."
                        logger.error(remarks)
                        signal.status = OrderStatus.ORDER_REJECTED
                        signal.remarks = remarks
                        return False, remarks, None

                    fund_data = fund_resp.get("data", {})
                    avail_bal = float(
                        fund_data.get("availabelBalance")
                        or fund_data.get("availableBalance")
                        or fund_data.get("sodLimit")
                        or 0.0
                    )

                    if avail_bal <= 0:
                        remarks = f"❌ [LIVE ORDER REJECTED] {opt.symbol}: Available broker balance is zero or unavailable (Available: ₹{avail_bal:,.2f})."
                        logger.error(remarks)
                        signal.status = OrderStatus.ORDER_REJECTED
                        signal.remarks = remarks
                        return False, remarks, None

                    if avail_bal < required_margin:
                        remarks = (
                            f"❌ [LIVE ORDER REJECTED] {opt.symbol}: Insufficient broker margin. "
                            f"Required ₹{required_margin:,.2f}, Available: ₹{avail_bal:,.2f}."
                        )
                        logger.error(remarks)
                        signal.status = OrderStatus.ORDER_REJECTED
                        signal.remarks = remarks
                        return False, remarks, None

                except Exception as margin_exc:
                    remarks = f"❌ [LIVE ORDER REJECTED] {opt.symbol}: Broker fund limit check exception: {margin_exc}"
                    logger.error(remarks)
                    signal.status = OrderStatus.ORDER_REJECTED
                    signal.remarks = remarks
                    return False, remarks, None
                order_resp = dhan.place_super_order(
                    security_id=opt.security_id,
                    exchange_segment=dhan.NSE_FNO,
                    transaction_type=dhan.BUY,
                    quantity=qty,
                    order_type=dhan.LIMIT,
                    product_type=dhan_prod,
                    price=levels.entry_price,
                    targetPrice=levels.target_price,
                    stopLossPrice=levels.stop_loss_price,
                    trailingJump=levels.trailing_jump,
                    tag="st14_bull_ce",
                )

                if isinstance(order_resp, dict) and order_resp.get("status") == "success":
                    live_order_id = str(order_resp.get("data", {}).get("orderId", "LIVE_ORDER"))
                    remarks = (
                        f"🚀 [LIVE SUPER ORDER PLACED] {qty} qty {opt.symbol} @ ₹{levels.entry_price:.2f} "
                        f"(Order ID: {live_order_id})"
                    )
                    logger.info(remarks)
                    position = St14Position(
                        position_id=live_order_id,
                        symbol=opt.underlying_symbol,
                        option_symbol=opt.symbol,
                        security_id=opt.security_id,
                        quantity=qty,
                        entry_price=levels.entry_price,
                        current_ltp=levels.entry_price,
                        target_price=levels.target_price,
                        stop_loss_price=levels.stop_loss_price,
                        product_type=self.config.product_type,
                        mode=ExecutionMode.LIVE,
                        entry_time_ist=now_ist_str,
                    )
                    self.active_positions[live_order_id] = position
                    self._executed_signal_ids.add(signal.signal_id)
                    self._executed_order_keys.add(idempotency_key)
                    self._persist_executed_order(idempotency_key, signal.signal_id, live_order_id, opt.underlying_symbol)
                    signal.status = OrderStatus.ORDER_PLACED
                    signal.order_id = live_order_id
                    return True, remarks, position
                else:
                    err_msg = order_resp.get("remarks") if isinstance(order_resp, dict) else str(order_resp)
                    remarks = f"❌ [LIVE ORDER REJECTED] {opt.symbol}: {err_msg}"
                    logger.error(remarks)
                    signal.status = OrderStatus.ORDER_REJECTED
                    signal.remarks = remarks
                    return False, remarks, None
            except Exception as exc:
                remarks = f"❌ [LIVE ORDER EXCEPTION] {opt.symbol}: {exc}"
                logger.error(remarks)
                signal.status = OrderStatus.ORDER_REJECTED
                signal.remarks = remarks
                return False, remarks, None

    def run_iteration(self, bypass_timing: bool = False) -> Dict[str, Any]:
        """Run full iteration (hourly discovery scan + 5-minute trigger check)."""
        if not self.config.enabled or self.config.status != "ACTIVE":
            return {
                "status": "PAUSED",
                "message": "Strategy Engine is PAUSED. Polling & execution suspended.",
                "signals": [],
                "orders_placed": 0,
                "breadth": self._last_breadth_status,
                "watchlist": [item.to_dict() for item in self.breakout_watchlist.values()],
            }

        disc_res = self.run_hourly_discovery_scan(bypass_timing=bypass_timing)
        trig_res = self.run_5min_trigger_monitor(bypass_timing=bypass_timing)

        return {
            "status": "COMPLETED",
            "signals": [s.to_dict() for s in self.signals_history[-15:]],
            "orders_placed": trig_res.get("orders_placed", 0),
            "executed_positions": trig_res.get("executed_positions", []),
            "breadth": self._last_breadth_status,
            "watchlist": [item.to_dict() for item in self.breakout_watchlist.values()],
            "discovery": disc_res,
            "trigger_monitor": trig_res,
        }

    def toggle_status(self, new_status: Optional[str] = None) -> str:
        """Toggle or set engine operational status (ACTIVE or PAUSED)."""
        target = new_status.upper() if new_status else ("PAUSED" if self.config.status == "ACTIVE" else "ACTIVE")
        if target not in ("ACTIVE", "PAUSED"):
            target = "ACTIVE"
        self.config.status = target
        self.config.enabled = (target == "ACTIVE")
        return target

    def toggle_mode(self, new_mode: Optional[str] = None) -> str:
        """Toggle or set execution mode (VIRTUAL or LIVE)."""
        if new_mode:
            target = ExecutionMode(new_mode.upper())
        else:
            target = ExecutionMode.LIVE if self.config.mode == ExecutionMode.VIRTUAL else ExecutionMode.VIRTUAL
        self.config.mode = target
        return target.value

    def toggle_auto_order(self, enabled: Optional[bool] = None) -> bool:
        """Toggle or set auto order placement flag."""
        if enabled is not None:
            self.config.auto_order = bool(enabled)
        else:
            self.config.auto_order = not self.config.auto_order
        return self.config.auto_order

    def toggle_product_type(self, new_prod: Optional[str] = None) -> str:
        """Toggle or set product type (INTRADAY or DELIVERY)."""
        if new_prod:
            target = ProductType(new_prod.upper())
        else:
            target = ProductType.DELIVERY if self.config.product_type == ProductType.INTRADAY else ProductType.INTRADAY
        self.config.product_type = target
        return target.value

    def _execute_broker_square_off(
        self,
        pos: St14Position,
        reason: str,
        now_str: str,
    ) -> Tuple[bool, str]:
        """Execute broker-level Super Order cancellation, position reconciliation, and market exit."""
        if pos.mode != ExecutionMode.LIVE or not self.provider or not self.provider.dhan:
            pos.status = "CLOSED"
            pos.close_reason = reason
            pos.exit_price = pos.current_ltp
            pos.exit_time_ist = now_str
            return True, "Virtual square-off completed"

        dhan = self.provider.dhan
        order_id = pos.position_id

        # 1. Inspect Super Order status from broker
        order_status = None
        if order_id and not order_id.startswith("SIM_"):
            try:
                order_info = dhan.get_order_by_id(order_id)
                if isinstance(order_info, dict) and order_info.get("status") == "success":
                    data = order_info.get("data", {})
                    if isinstance(data, dict):
                        order_status = data.get("orderStatus")
            except Exception as e:
                logger.warning("Could not query order %s status from Dhan: %s", order_id, e)

        # 2. Cancel order legs based on entry leg state
        if order_id and not order_id.startswith("SIM_"):
            if order_status in ("PENDING", "TRANSIT"):
                # Entry is still pending -> cancel ENTRY_LEG to cancel entire Super Order
                try:
                    c_resp = dhan.cancel_super_order(order_id, "ENTRY_LEG")
                    logger.info("🛑 Cancelled pending ENTRY_LEG for %s (%s): %s", pos.symbol, order_id, c_resp)
                except Exception as e:
                    logger.warning("Failed to cancel ENTRY_LEG for %s (%s): %s", pos.symbol, order_id, e)
            else:
                # Traded or unknown -> Cancel child exit legs (TARGET and STOP_LOSS)
                for leg in ("TARGET_LEG", "STOP_LOSS_LEG"):
                    try:
                        c_resp = dhan.cancel_super_order(order_id, leg)
                        logger.debug("Cancelled %s for %s (%s): %s", leg, pos.symbol, order_id, c_resp)
                    except Exception as e:
                        logger.debug("Could not cancel %s for %s (%s): %s", leg, pos.symbol, order_id, e)

                # Fallback cancel regular order if not a super order
                try:
                    dhan.cancel_order(order_id)
                except Exception:
                    pass

        # 3. Query broker-confirmed open positions
        net_qty = 0
        try:
            pos_resp = dhan.get_positions()
            positions_list = []
            if isinstance(pos_resp, dict) and pos_resp.get("status") == "success":
                positions_list = pos_resp.get("data", [])
            elif isinstance(pos_resp, list):
                positions_list = pos_resp
            elif isinstance(pos_resp, dict) and pos_resp.get("status") == "failure":
                err_msg = f"Dhan get_positions returned failure: {pos_resp.get('remarks', pos_resp)}"
                logger.error("❌ %s", err_msg)
                pos.status = "EXIT_FAILED"
                pos.close_reason = err_msg
                return False, err_msg

            for p in positions_list:
                if not isinstance(p, dict):
                    continue
                # Match by securityId or tradingSymbol
                p_sec = str(p.get("securityId", "")).strip()
                p_sym = str(p.get("tradingSymbol", "")).strip()
                if (pos.security_id and p_sec == str(pos.security_id)) or (pos.option_symbol and p_sym == pos.option_symbol):
                    net_qty = int(p.get("netQty", 0))
                    if net_qty == 0 and "buyQty" in p and "sellQty" in p:
                        net_qty = int(p.get("buyQty", 0)) - int(p.get("sellQty", 0))
                    break
        except Exception as p_err:
            err_msg = f"Failed to fetch broker position book for {pos.symbol}: {p_err}"
            logger.error("❌ %s", err_msg)
            pos.status = "EXIT_FAILED"
            pos.close_reason = err_msg
            return False, err_msg

        # 4. If broker reports netQty > 0, dispatch market SELL order with price=0.0
        if net_qty > 0:
            try:
                dhan_prod = dhan.INTRA if pos.product_type == ProductType.INTRADAY else dhan.MARGIN
                exit_resp = dhan.place_order(
                    security_id=str(pos.security_id),
                    exchange_segment=dhan.NSE_FNO,
                    transaction_type=dhan.SELL,
                    quantity=net_qty,
                    order_type=dhan.MARKET,
                    product_type=dhan_prod,
                    price=0.0,
                    tag="st14_sqoff",
                )
                if isinstance(exit_resp, dict) and exit_resp.get("status") == "success":
                    exit_order_id = str(exit_resp.get("data", {}).get("orderId", "EXIT_ORDER"))
                    logger.info("📤 Dispatched Live Square-Off Exit Order for %s: %s (Qty: %d)", pos.symbol, exit_order_id, net_qty)
                    pos.status = "CLOSED"
                    pos.close_reason = f"{reason} (Exit Order: {exit_order_id})"
                    pos.exit_price = pos.current_ltp
                    pos.exit_time_ist = now_str
                    return True, f"Exit order {exit_order_id} placed"
                else:
                    err_msg = f"Broker exit order rejected for {pos.symbol}: {exit_resp}"
                    logger.error("❌ %s", err_msg)
                    pos.status = "EXIT_FAILED"
                    pos.close_reason = err_msg
                    return False, err_msg
            except Exception as e_err:
                err_msg = f"Exception placing broker exit order for {pos.symbol}: {e_err}"
                logger.error("❌ %s", err_msg)
                pos.status = "EXIT_FAILED"
                pos.close_reason = err_msg
                return False, err_msg
        else:
            # Already flat at broker (e.g. entry canceled or already filled/exited)
            logger.info("ℹ️ Position %s already flat at broker (netQty: %d). Marking closed.", pos.symbol, net_qty)
            pos.status = "CLOSED"
            pos.close_reason = f"{reason} (Broker netQty: 0)"
            pos.exit_price = pos.current_ltp
            pos.exit_time_ist = now_str
            return True, "Position already flat at broker"

    def emergency_square_off_all(self) -> List[St14Position]:
        """Close all active positions immediately, canceling pending orders and placing market exits on Dhan."""
        with self._lock:
            closed: List[St14Position] = []
            now_str = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
            for pos_id, pos in list(self.active_positions.items()):
                success, _ = self._execute_broker_square_off(
                    pos=pos,
                    reason="Emergency Square-Off Requested",
                    now_str=now_str,
                )
                if success:
                    closed.append(pos)
                    self.closed_positions.append(pos)
                    del self.active_positions[pos_id]
                else:
                    logger.error("⚠️ Failed to square off position %s (%s). Retaining in active positions.", pos.symbol, pos_id)
            return closed

    def square_off_intraday_positions(self, target_dt: Optional[datetime] = None) -> List[St14Position]:
        """Enforce 15:00 (3:00 PM IST) auto square-off for all open intraday positions."""
        with self._lock:
            closed: List[St14Position] = []
            now_str = (target_dt or datetime.now(ZoneInfo("Asia/Kolkata"))).strftime("%Y-%m-%d %H:%M:%S")

            for pos_id, pos in list(self.active_positions.items()):
                if pos.product_type == ProductType.INTRADAY:
                    success, _ = self._execute_broker_square_off(
                        pos=pos,
                        reason="3:00 PM Intraday Auto Square-Off",
                        now_str=now_str,
                    )
                    if success:
                        closed.append(pos)
                        self.closed_positions.append(pos)
                        del self.active_positions[pos_id]
                        logger.info("⏰ Closed Intraday Position for %s: %s (P&L: ₹%s)", pos.symbol, pos.close_reason, pos.unrealized_pnl)
                    else:
                        logger.error("⚠️ Failed auto square-off for intraday position %s (%s). Retaining in active positions.", pos.symbol, pos_id)

            return closed

    def get_strategy_telemetry(self) -> Dict[str, Any]:
        """Aggregate real-time metrics for dashboard monitoring."""
        open_pos_list = [p.to_dict() for p in self.active_positions.values()]
        closed_pos_list = [p.to_dict() for p in self.closed_positions]
        total_pnl = sum(p.unrealized_pnl for p in self.active_positions.values()) + sum(
            p.unrealized_pnl for p in self.closed_positions
        )
        watchlist_items = [item.to_dict() for item in self.breakout_watchlist.values()]
        active_watching = len([i for i in self.breakout_watchlist.values() if i.status == OrderStatus.WAITING_TRIGGER])

        breadth_data = self._last_breadth_status
        if not breadth_data:
            try:
                _, breadth_data = check_market_breadth(provider=self.provider)
                self._last_breadth_status = breadth_data
            except Exception:
                pass

        return {
            "strategy_id": "st14_bullish_ce",
            "name": "ST-14: Bullish CE Options Trading Strategy",
            "status": self.config.status,
            "enabled": self.config.enabled,
            "mode": self.config.mode.value,
            "execution_mode": self.config.mode.value,
            "auto_order": self.config.auto_order,
            "auto_order_enabled": self.config.auto_order,
            "product_type": self.config.product_type.value,
            "trade_cutoff_time": self.config.trade_cutoff_time,
            "square_off_time": self.config.square_off_time,
            "capital_per_trade": self.config.capital_per_trade,
            "target_profit_pct": self.config.target_profit_pct,
            "stop_loss_pct": self.config.stop_loss_pct,
            "trailing_jump_pts": self.config.trailing_jump_pts,
            "active_positions_count": len(self.active_positions),
            "total_pnl": round(total_pnl, 2),
            "market_breadth": breadth_data,
            "last_hourly_scan_time": self.last_hourly_scan_time,
            "last_5min_check_time": self.last_5min_check_time,
            "last_hourly_candidates_count": self.last_hourly_candidates_count,
            "active_watchlist_count": active_watching,
            "breakout_watchlist": watchlist_items,
            "active_positions": open_pos_list,
            "closed_positions": closed_pos_list,
            "recent_signals": [s.to_dict() for s in self.signals_history[-15:]],
        }



