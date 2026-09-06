"""Basic test suite for project smoke testing."""

import unittest
from news_based_strategy import __version__
from news_based_strategy.config import settings


class TestProjectSetup(unittest.TestCase):
    """Test basic project configuration and imports."""

    def test_version(self):
        """Ensure version is defined."""
        self.assertIsNotNone(__version__)
        self.assertTrue(len(__version__) > 0)

    def test_settings_loaded(self):
        """Ensure default settings load correctly."""
        self.assertIsNotNone(settings.app_env)
        self.assertIsNotNone(settings.log_level)


if __name__ == "__main__":
    unittest.main()

