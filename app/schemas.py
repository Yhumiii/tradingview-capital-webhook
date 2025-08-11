# app/schemas.py
from pydantic import BaseModel, field_validator
from typing import Optional

class TradingViewAlert(BaseModel):
    symbol: str
    side: str                # "buy" or "sell"
    price: Optional[float] = None
    qty: Optional[float] = None    # optional; if absent we'll size from cash_pct
    cash_pct: Optional[float] = 0.10  # fraction of 'available' balance to deploy (e.g., 0.10)
    sl_pct: Optional[float] = 0.10    # 10% stop by default
    take_profit: Optional[float] = None
    secret: Optional[str] = None

    @field_validator("side")
    @classmethod
    def norm_side(cls, v):
        v = v.lower()
        if v not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        return v
