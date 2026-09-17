"""Pydantic request schemas for UI and API endpoints."""

from typing import Optional
from pydantic import BaseModel


class AppLoginRequest(BaseModel):
    username: str
    password: str


class PlaceOrderRequest(BaseModel):
    seq_id: str
    symbol: str
    action: str = "BUY"
    product_type: str = "INTRADAY"
    confidence: int = 90
    catalyst_type: str = "ORDER_WIN"
    summary: str = ""
    ltp: Optional[float] = None


class ToggleAutoOrderRequest(BaseModel):
    auto_order: bool


class ToggleDryRunRequest(BaseModel):
    dry_run: bool


class UpdateTokenRequest(BaseModel):
    access_token: str
    client_id: Optional[str] = None
    dry_run: Optional[bool] = None


class SaveApiKeysRequest(BaseModel):
    client_id: Optional[str] = None
    app_id: str
    app_secret: str


class LoadHistoryRequest(BaseModel):
    today_only: bool = False
    date_str: Optional[str] = None


class ToggleStrategyStatusRequest(BaseModel):
    status: Optional[str] = None


class ToggleStrategyModeRequest(BaseModel):
    mode: Optional[str] = None


class ToggleStrategyAutoOrderRequest(BaseModel):
    auto_order: Optional[bool] = None


class ToggleStrategyProductRequest(BaseModel):
    product_type: Optional[str] = None


class St14ExecuteSignalRequest(BaseModel):
    signal_id: str


class St14ConfigUpdateRequest(BaseModel):
    mode: Optional[str] = None
    product_type: Optional[str] = None
    auto_order: Optional[bool] = None
    capital_per_trade: Optional[float] = None
    target_profit_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    trailing_jump_pts: Optional[float] = None
    trade_cutoff_time: Optional[str] = None
    square_off_time: Optional[str] = None


__all__ = [
    "AppLoginRequest",
    "PlaceOrderRequest",
    "ToggleAutoOrderRequest",
    "ToggleDryRunRequest",
    "UpdateTokenRequest",
    "SaveApiKeysRequest",
    "LoadHistoryRequest",
    "ToggleStrategyStatusRequest",
    "ToggleStrategyModeRequest",
    "ToggleStrategyAutoOrderRequest",
    "ToggleStrategyProductRequest",
    "St14ExecuteSignalRequest",
    "St14ConfigUpdateRequest",
]


