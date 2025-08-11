# app/schemas.py
from pydantic import BaseModel, field_validator
from typing import Optional

class TradingViewAlert(BaseModel):
    # You can tailor this to your alert JSON
    symbol: str
    side: str                # "buy" or "sell"
    qty: float
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    secret: Optional[str] = None

    @field_validator("side")
    @classmethod
    def norm_side(cls, v):
        v = v.lower()
        if v not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        return v
# (Paste the schemas.py code from the tutorial here)
