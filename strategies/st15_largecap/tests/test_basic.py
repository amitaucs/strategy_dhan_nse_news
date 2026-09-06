"""Basic scaffold tests for ST15_LargeCap."""

import unittest
from st15_largecap.config import settings


class TestST15Basic(unittest.TestCase):
    """Test configuration and initialization."""

    def test_default_config(self):
        self.assertEqual(settings.ui_port, 8015)
        self.assertEqual(settings.universe_type, "NIFTY_200")
        self.assertTrue(settings.dry_run)
        self.assertEqual(settings.EMA_PROXIMITY_PCT, 0.5)
        self.assertEqual(settings.RISK_REWARD_RATIO, 3.0)


if __name__ == "__main__":
    unittest.main()
