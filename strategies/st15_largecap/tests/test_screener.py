"""Unit tests for ST15 Screener multi-gate verification and signal generation."""

from datetime import datetime, timedelta
import unittest

from st15_largecap.core.models import Candle, SetupSignal, SignalStatus
from st15_largecap.engine.screener import ST15Screener
from st15_largecap.ingestion.candles import generate_mock_2h_candles


class TestScreener(unittest.TestCase):
    def test_screener_empty_candles(self):
        screener = ST15Screener()
        res = screener.evaluate(symbol="TEST", sec_id="123", candles=[])
        self.assertFalse(res.is_setup_ready)
        self.assertIsNone(res.signal)

    def test_screener_bullish_pullback_trigger(self):
        # Generate 80 candles with strong bullish trend and dip + bounce at end
        candles = generate_mock_2h_candles(
            symbol="RELIANCE",
            base_price=2800.0,
            num_candles=80,
            bullish_trend=True,
            pullback_at_end=True,
        )

        screener = ST15Screener(
            ema_proximity_pct=1.5,
            risk_reward_ratio=3.0,
        )
        res = screener.evaluate(symbol="RELIANCE", sec_id="2885", candles=candles)

        self.assertEqual(res.candles_count, 80)
        self.assertEqual(res.symbol, "RELIANCE")
        self.assertTrue(res.is_ema_stacked)
        self.assertTrue(res.is_supertrend_green)
        self.assertTrue(res.is_ha_green)

        # Check setup signal if ready
        if res.is_setup_ready:
            self.assertIsNotNone(res.signal)
            self.assertGreater(res.signal.trigger_price, res.signal.stop_loss_price)
            self.assertGreater(res.signal.target_profit_price, res.signal.trigger_price)
            expected_target = round(
                res.signal.trigger_price + (res.signal.risk_per_share * 3.0), 2
            )
            self.assertEqual(res.signal.target_profit_price, expected_target)
            self.assertEqual(res.signal.risk_reward_ratio, 3.0)

    def test_case_a_first_green_ha_when_supertrend_already_green(self):
        """Case A: 1st Green Heikin Ashi candle after pullback when SuperTrend is already Green."""
        candles = generate_mock_2h_candles(
            symbol="INFY",
            base_price=1500.0,
            num_candles=80,
            bullish_trend=True,
            pullback_at_end=False,
        )
        base_time = candles[-1].timestamp

        # Add 3 red pullback candles dipping near 20 EMA
        last_close = candles[-1].close
        for i in range(1, 4):
            c_open = last_close
            c_close = c_open * 0.995
            candles.append(Candle(
                timestamp=base_time + timedelta(hours=2 * i),
                open=round(c_open, 2),
                high=round(c_open * 1.001, 2),
                low=round(c_close * 0.999, 2),
                close=round(c_close, 2),
                volume=10000.0,
            ))
            last_close = c_close

        # Add 1st Green HA candle (bounce reversal)
        c_open = last_close
        c_close = c_open * 1.015
        candles.append(Candle(
            timestamp=base_time + timedelta(hours=8),
            open=round(c_open, 2),
            high=round(c_close * 1.005, 2),
            low=round(c_open * 0.998, 2),
            close=round(c_close, 2),
            volume=25000.0,
        ))

        screener = ST15Screener(ema_proximity_pct=2.0)
        res = screener.evaluate(symbol="INFY", sec_id="1594", candles=candles)

        self.assertTrue(res.is_ema_stacked)
        self.assertTrue(res.is_in_dip)
        self.assertTrue(res.is_ha_green)
        self.assertTrue(res.is_supertrend_green)
        self.assertTrue(res.is_setup_ready)
        self.assertIsNotNone(res.signal)

    def test_case_c_move_in_progress_rejection(self):
        """Case C: Move is in progress (e.g. 5th consecutive green candle), should NOT generate new signal."""
        candles = generate_mock_2h_candles(
            symbol="TCS",
            base_price=3500.0,
            num_candles=80,
            bullish_trend=True,
            pullback_at_end=False,
        )
        base_time = candles[-1].timestamp

        # Add 5 consecutive strong green candles
        last_close = candles[-1].close
        for i in range(1, 6):
            c_open = last_close
            c_close = c_open * 1.01
            candles.append(Candle(
                timestamp=base_time + timedelta(hours=2 * i),
                open=round(c_open, 2),
                high=round(c_close * 1.005, 2),
                low=round(c_open * 0.998, 2),
                close=round(c_close, 2),
                volume=20000.0,
            ))
            last_close = c_close

        screener = ST15Screener(ema_proximity_pct=5.0)
        res = screener.evaluate(symbol="TCS", sec_id="11536", candles=candles)

        self.assertTrue(res.is_ha_green)
        self.assertTrue(res.is_supertrend_green)
        # Should be rejected because it is 5th+ green candle, not the 1st green candle or ST flip
        self.assertFalse(res.is_setup_ready)
        self.assertIn("Move in-progress", res.invalidation_reason)
        self.assertIsNone(res.signal)

    def test_validate_setup_signal(self):
        """Test validate_setup_signal for active, stop loss breach, and bearish reversal conditions."""
        candles = generate_mock_2h_candles(
            symbol="HDFCBANK",
            base_price=1600.0,
            num_candles=80,
            bullish_trend=True,
            pullback_at_end=True,
        )
        screener = ST15Screener(ema_proximity_pct=2.0)
        res = screener.evaluate(symbol="HDFCBANK", sec_id="1333", candles=candles)
        self.assertTrue(res.is_setup_ready)
        self.assertIsNotNone(res.signal)
        sig = res.signal

        # 1. Valid Active setup
        is_valid, msg = screener.validate_setup_signal(sig, candles)
        self.assertTrue(is_valid)
        self.assertIn("Active", msg)

        # 2. Stop loss breached
        sig_breached = SetupSignal(
            symbol="HDFCBANK",
            sec_id="1333",
            setup_time=datetime.now(),
            trigger_price=sig.trigger_price,
            stop_loss_price=candles[-1].close + 50.0,  # SL higher than LTP
            target_profit_price=sig.target_profit_price + 200.0,
            risk_per_share=70.0,
            risk_reward_ratio=3.0,
            ema_20=sig.ema_20,
            ema_50=sig.ema_50,
            ema_200=sig.ema_200,
            supertrend=sig.supertrend,
            status=SignalStatus.TRIGGERED,
        )
        is_valid, msg = screener.validate_setup_signal(sig_breached, candles)
        self.assertFalse(is_valid)
        self.assertIn("breached Stop Loss", msg)

        # 3. Heikin Ashi turns Red (Bearish) while price is above SL
        bearish_candles = list(candles)
        last_t = bearish_candles[-1].timestamp
        bearish_candles.append(Candle(
            timestamp=last_t + timedelta(hours=2),
            open=1850.0,
            high=1850.0,
            low=1835.0,
            close=1838.0,
            volume=50000.0,
        ))
        is_valid, msg = screener.validate_setup_signal(sig, bearish_candles)
        self.assertFalse(is_valid)
        self.assertIn("Red", msg)

    def test_axisbank_inverted_ema_rejection(self):
        """Verify AXISBANK exhibits bearish 200 > 50 > 20 EMA and is correctly rejected with detailed reason."""
        candles = generate_mock_2h_candles(symbol="AXISBANK", num_candles=250)
        screener = ST15Screener()
        res = screener.evaluate(symbol="AXISBANK", sec_id="5900", candles=candles)

        self.assertFalse(res.is_ema_stacked)
        self.assertFalse(res.is_setup_ready)
        self.assertIsNone(res.signal)
        self.assertGreater(res.ema_200, res.ema_50)
        self.assertGreater(res.ema_50, res.ema_20)
        self.assertIn("Inverted (200 > 50 > 20 EMA", res.invalidation_reason)


if __name__ == "__main__":
    unittest.main()

