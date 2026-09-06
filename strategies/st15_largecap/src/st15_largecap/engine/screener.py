"""ST15 Large-Cap Strategy Screener and Rule Verification Engine."""

from datetime import datetime
import logging
from typing import List, Optional

from st15_largecap.config import settings
from st15_largecap.core.models import Candle, ScanResult, SetupSignal, SignalStatus
from st15_largecap.indicators.ema import (
    calculate_triple_ema,
    check_ema_proximity,
    is_ema_stacked_bullish,
)
from st15_largecap.indicators.supertrend import calculate_supertrend
from st15_largecap.indicators.swing import calculate_swing_low
from st15_largecap.ingestion.heikin_ashi import calculate_heikin_ashi

logger = logging.getLogger(__name__)


class ST15Screener:
    """Evaluates 2H candle series against ST15 Large-Cap momentum rules."""

    def __init__(
        self,
        ema_proximity_pct: float = settings.EMA_PROXIMITY_PCT,
        supertrend_period: int = settings.SUPERTREND_PERIOD,
        supertrend_multiplier: float = settings.SUPERTREND_MULTIPLIER,
        swing_low_lookback: int = settings.SWING_LOW_LOOKBACK,
        risk_reward_ratio: float = settings.RISK_REWARD_RATIO,
    ):
        self.ema_proximity_pct = ema_proximity_pct
        self.supertrend_period = supertrend_period
        self.supertrend_multiplier = supertrend_multiplier
        self.swing_low_lookback = swing_low_lookback
        self.risk_reward_ratio = risk_reward_ratio

    def evaluate(
        self,
        symbol: str,
        sec_id: str,
        candles: List[Candle],
    ) -> ScanResult:
        """Scan a symbol's 2H candles and determine if an entry setup has triggered.
        
        Rules:
          1. Bullish EMA Alignment: 20 EMA > 50 EMA > 200 EMA
          2. Pullback Dip: Recent price pulled back near or touched 20/50/200 EMA within proximity %
          3. Heikin Ashi: First Green HA candle (HA_Close > HA_Open) after dip/red HA candle
          4. SuperTrend: SuperTrend is Green (Bullish) on current candle
        """
        if not candles or len(candles) < 20:
            ltp = candles[-1].close if candles else 0.0
            return ScanResult(
                symbol=symbol,
                sec_id=sec_id,
                ltp=ltp,
                ema_20=0.0,
                ema_50=0.0,
                ema_200=0.0,
                is_ema_stacked=False,
                is_in_dip=False,
                nearest_ema="",
                nearest_ema_dist_pct=999.0,
                is_ha_green=False,
                is_supertrend_green=False,
                is_setup_ready=False,
                candles_count=len(candles),
            )

        # 1. Calculate Indicators
        closes = [c.close for c in candles]
        ema_dict = calculate_triple_ema(
            closes,
            fast_span=settings.EMA_FAST,
            mid_span=settings.EMA_MID,
            slow_span=settings.EMA_SLOW,
        )
        ema_20_list = ema_dict["ema_20"]
        ema_50_list = ema_dict["ema_50"]
        ema_200_list = ema_dict["ema_200"]

        st_vals, st_green_list = calculate_supertrend(
            candles,
            period=self.supertrend_period,
            multiplier=self.supertrend_multiplier,
        )

        ha_candles = calculate_heikin_ashi(candles)

        curr_idx = len(candles) - 1
        curr_candle = candles[curr_idx]
        curr_ha = ha_candles[curr_idx]
        prev_ha = ha_candles[curr_idx - 1] if curr_idx > 0 else curr_ha

        ema_20 = ema_20_list[curr_idx]
        ema_50 = ema_50_list[curr_idx]
        ema_200 = ema_200_list[curr_idx]
        is_st_green = st_green_list[curr_idx]
        st_val = st_vals[curr_idx]

        # Gate 1: Bullish EMA Alignment (Strict 20 EMA > 50 EMA > 200 EMA)
        is_ema_stacked = is_ema_stacked_bullish(ema_20, ema_50, ema_200)

        # Gate 2: Pullback Dip near or kissing any EMA
        # Only valid if Gate 1 (Bullish EMA stack) passes
        is_in_dip = False
        nearest_ema = ""
        min_dist_pct = 999.0

        if is_ema_stacked:
            lookback_dip = min(4, len(candles))
            for offset in range(lookback_dip):
                idx = curr_idx - offset
                c = candles[idx]
                dip_ok, name, dist = check_ema_proximity(
                    low=c.low,
                    high=c.high,
                    close=c.close,
                    ema_20=ema_20_list[idx],
                    ema_50=ema_50_list[idx],
                    ema_200=ema_200_list[idx],
                    tolerance_pct=self.ema_proximity_pct,
                )
                if dist < min_dist_pct:
                    min_dist_pct = dist
                    nearest_ema = name
                if dip_ok:
                    is_in_dip = True
        else:
            # When EMA is inverted/not stacked, compute nearest EMA for informational distance only
            _, nearest_ema, min_dist_pct = check_ema_proximity(
                low=curr_candle.low,
                high=curr_candle.high,
                close=curr_candle.close,
                ema_20=ema_20,
                ema_50=ema_50,
                ema_200=ema_200,
                tolerance_pct=self.ema_proximity_pct,
            )
            is_in_dip = False

        # Gate 3 & 4: First Heikin Ashi Green Candle after pullback & SuperTrend Timing
        # Rule: Buy signal only generates on:
        #   Case A: 1st Green HA candle after pullback, when SuperTrend is already Green (or turns green)
        #   Case B: When SuperTrend becomes Green (bullish flip) after the 1st green HA candle (candles 1-3 of bounce)
        is_curr_ha_green = curr_ha.is_green or (curr_ha.close >= curr_ha.open)
        consecutive_green_ha = 0
        if is_curr_ha_green:
            for k in range(curr_idx, -1, -1):
                if ha_candles[k].is_green or (ha_candles[k].close >= ha_candles[k].open):
                    consecutive_green_ha += 1
                else:
                    break

        # SuperTrend Status
        is_st_green = bool(st_green_list[curr_idx])
        prev_st_green = bool(st_green_list[curr_idx - 1]) if curr_idx > 0 else False
        st_just_turned_green = is_st_green and not prev_st_green

        # Trigger conditions
        trigger_first_green = (consecutive_green_ha == 1) and is_st_green
        trigger_st_flip_after_green = st_just_turned_green and (1 <= consecutive_green_ha <= 3)
        is_trigger_event = trigger_first_green or trigger_st_flip_after_green

        is_supertrend_green = is_st_green

        # Overall Setup Trigger Verification & Invalidation Reason Determination
        is_setup_ready = (
            is_ema_stacked
            and is_in_dip
            and is_curr_ha_green
            and is_st_green
            and is_trigger_event
        )

        invalidation_reason = ""
        if not is_ema_stacked:
            if ema_200 > ema_50 and ema_50 > ema_20:
                invalidation_reason = f"EMA: Inverted (200 > 50 > 20 EMA: ₹{ema_200:.1f} > ₹{ema_50:.1f} > ₹{ema_20:.1f})"
            elif ema_200 > ema_50:
                invalidation_reason = f"EMA: 200 EMA (₹{ema_200:.1f}) > 50 EMA (₹{ema_50:.1f})"
            elif ema_50 > ema_20:
                invalidation_reason = f"EMA: 50 EMA (₹{ema_50:.1f}) > 20 EMA (₹{ema_20:.1f})"
            else:
                invalidation_reason = "EMA: 20/50/200 EMAs Not Stacked"
        elif not is_in_dip:
            invalidation_reason = f"Dip: Distance ({min_dist_pct:+.2f}%) exceeds tolerance"
        elif not is_curr_ha_green:
            invalidation_reason = "HA: Candle is Red (In Pullback)"
        elif not is_st_green:
            invalidation_reason = "SuperTrend: Bearish (Red - waiting for flip)"
        elif not is_trigger_event:
            if consecutive_green_ha > 1:
                invalidation_reason = f"HA: Move in-progress ({consecutive_green_ha}th green candle, trigger was on 1st candle or ST flip)"
            else:
                invalidation_reason = "Trigger: Waiting for 1st green HA or SuperTrend flip"

        # Calculate Swing Low for Protective SL
        swing_low = calculate_swing_low(
            candles,
            lookback=self.swing_low_lookback,
            buffer_pct=0.1,
        )

        signal: Optional[SetupSignal] = None
        if is_setup_ready:
            # Trigger price = High of the confirmation candle (or HA High)
            trigger_price = round(max(curr_candle.high, curr_ha.high), 2)
            stop_loss = round(min(swing_low, trigger_price * 0.98), 2) # Ensure SL is strictly below trigger
            risk_per_share = round(trigger_price - stop_loss, 2)
            
            if risk_per_share <= 0:
                risk_per_share = round(trigger_price * 0.015, 2)
                stop_loss = round(trigger_price - risk_per_share, 2)

            target_profit = round(trigger_price + (risk_per_share * self.risk_reward_ratio), 2)

            signal = SetupSignal(
                symbol=symbol,
                sec_id=sec_id,
                setup_time=curr_candle.timestamp,
                trigger_price=trigger_price,
                stop_loss_price=stop_loss,
                target_profit_price=target_profit,
                risk_per_share=risk_per_share,
                risk_reward_ratio=self.risk_reward_ratio,
                ema_20=ema_20,
                ema_50=ema_50,
                ema_200=ema_200,
                supertrend=st_val,
                ha_close=curr_ha.close,
                ha_open=curr_ha.open,
                nearest_ema_name=nearest_ema,
                nearest_ema_dist_pct=min_dist_pct,
                status=SignalStatus.TRIGGERED,
                invalidation_reason="",
            )

        return ScanResult(
            symbol=symbol,
            sec_id=sec_id,
            ltp=curr_candle.close,
            ema_20=ema_20,
            ema_50=ema_50,
            ema_200=ema_200,
            is_ema_stacked=is_ema_stacked,
            is_in_dip=is_in_dip,
            nearest_ema=nearest_ema,
            nearest_ema_dist_pct=min_dist_pct,
            is_ha_green=is_curr_ha_green,
            is_supertrend_green=is_supertrend_green,
            is_setup_ready=is_setup_ready,
            swing_low=swing_low,
            signal=signal,
            candles_count=len(candles),
            invalidation_reason=invalidation_reason,
            scanned_at=datetime.now(),
        )

    def validate_setup_signal(self, signal: SetupSignal, candles: List[Candle]) -> tuple[bool, str]:
        """Verify if a previously generated signal is still valid in current market conditions.
        
        Returns:
            (is_valid: bool, status_message: str)
        """
        if not candles or len(candles) < 20:
            return False, "Insufficient candle data"

        curr_candle = candles[-1]
        # 1. Check if price fell below Stop Loss
        if signal.stop_loss_price and curr_candle.close < signal.stop_loss_price:
            return False, f"Price (₹{curr_candle.close:.2f}) breached Stop Loss (₹{signal.stop_loss_price:.2f})"

        # 2. Check if price exceeded Target significantly
        if signal.target_profit_price and curr_candle.close >= signal.target_profit_price:
            return False, f"Price (₹{curr_candle.close:.2f}) already reached Target (₹{signal.target_profit_price:.2f})"

        # 3. Check Heikin Ashi candle state (if HA turned red, the bounce failed)
        ha_candles = calculate_heikin_ashi(candles)
        curr_ha = ha_candles[-1]
        if curr_ha.is_red:
            return False, "Heikin Ashi turned Red (Bearish)"

        # 4. Check SuperTrend status (if SuperTrend turned red)
        st_vals, st_green_list = calculate_supertrend(
            candles,
            period=self.supertrend_period,
            multiplier=self.supertrend_multiplier,
        )
        if not st_green_list[-1]:
            return False, "SuperTrend turned Red (Bearish)"

        # 5. Check EMA alignment
        closes = [c.close for c in candles]
        ema_dict = calculate_triple_ema(
            closes,
            fast_span=settings.EMA_FAST,
            mid_span=settings.EMA_MID,
            slow_span=settings.EMA_SLOW,
        )
        if not is_ema_stacked_bullish(ema_dict["ema_20"][-1], ema_dict["ema_50"][-1], ema_dict["ema_200"][-1]):
            return False, "EMA alignment lost (20/50/200 EMAs no longer bullish stacked)"

        return True, "Setup is Active and Qualified"
