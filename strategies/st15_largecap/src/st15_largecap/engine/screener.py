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
        # Check current candle or any of the preceding 3 candles for proximity dip
        is_in_dip = False
        nearest_ema = ""
        min_dist_pct = 999.0

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

        # Gate 3: First Heikin Ashi Green Candle after a dip / red candle
        # The transition into an entry setup requires the current HA candle to be Green
        # and the immediately preceding HA candle to have been Red (or a reversal candle)
        is_curr_ha_green = curr_ha.is_green
        is_first_green = is_curr_ha_green and (prev_ha.is_red or (curr_idx >= 2 and ha_candles[curr_idx - 2].is_red and abs(prev_ha.close - prev_ha.open) < 0.05 * prev_ha.close))

        # Gate 4: SuperTrend Bullish (Green)
        is_supertrend_green = is_st_green

        # Overall Setup Trigger Verification
        is_setup_ready = (
            is_ema_stacked
            and is_in_dip
            and is_first_green
            and is_supertrend_green
        )

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
            scanned_at=datetime.now(),
        )
