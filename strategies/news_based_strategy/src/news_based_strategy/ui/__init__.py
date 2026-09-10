"""Web GUI Dashboard package for news-based trading strategy."""

from news_based_strategy.ui.server import create_app, run_server
from news_based_strategy.ui.state import DashboardState
from news_based_strategy.ui.routes import register_routes

__all__ = [
    "create_app",
    "run_server",
    "DashboardState",
    "register_routes",
]
