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


__all__ = [
    "AppLoginRequest",
    "PlaceOrderRequest",
    "ToggleAutoOrderRequest",
    "ToggleDryRunRequest",
    "UpdateTokenRequest",
    "SaveApiKeysRequest",
    "LoadHistoryRequest",
]

