# main.py
from typing import Optional, Dict, Any
import json
import re
import logging

from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, Field

# ------------------------------------------------------------------------------
# Pydantic config: ignore unknown fields.
# Works for v2 (model_config) and v1 (Config) with a single class definition.
# ------------------------------------------------------------------------------
class Alert(BaseModel):
    # Make everything optional because TradingView templates may omit fields.
    # Provide helpful aliases to be flexible with different templates.
    symbol: Optional[str] = Field(None, alias="ticker")
    action: Optional[str] = Field(None, alias="side")     # "buy" | "sell"
    price: Optional[float] = Field(None, alias="close")
    qty: Optional[float] = Field(None, alias="quantity")
    comment: Optional[str] = None
    # Add any fields your flow might need; keep them optional.

    class Config:  # Pydantic v1
        extra = "ignore"
        allow_population_by_field_name = True

    model_config = {  # Pydantic v2
        "extra": "ignore",
        "populate_by_name": True
    }

# ------------------------------------------------------------------------------
# App
# ------------------------------------------------------------------------------
app = FastAPI()
logger = logging.getLogger("uvicorn.error")

@app.get("/health")
def health():
    return {"status": "ok"}

def _parse_text_body_to_dict(text: str) -> Dict[str, Any]:
    """
    Try to salvage data from text bodies like:
      symbol=AAPL
      action=buy
      price=225.12
    or
      symbol: AAPL
      action: sell
      price: 224.8
    Returns {} if nothing meaningful is found.
    """
    data: Dict[str, Any] = {}
    for line in text.splitlines():
        m = re.match(r"\s*([A-Za-z0-9_\-\.]+)\s*[:=]\s*(.+?)\s*$", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2)
        # Try casting to float if numeric
        try:
            if re.match(r"^-?\d+(\.\d+)?$", v):
                v = float(v)
        except Exception:
            pass
        data[k] = v
    return data

async def _extract_payload(request: Request) -> Dict[str, Any]:
    """
    - If JSON: parse and return dict.
    - If text/plain: try to parse key/value lines; else wrap as {"raw": "..."}.
    """
    raw_bytes = await request.body()
    raw_str = raw_bytes.decode("utf-8", errors="replace")
    ctype = request.headers.get("content-type", "")

    logger.info(f"[webhook] content-type={ctype}")
    logger.info(f"[webhook] raw (first 500B)={raw_str[:500]}")

    # Try JSON first regardless of header (some send JSON with text/plain)
    try:
        return json.loads(raw_str)
    except Exception:
        pass

    # Try to salvage from plain text lines
    kv = _parse_text_body_to_dict(raw_str)
    if kv:
        return kv

    # Last resort: return as raw text
    return {"raw": raw_str}

def _validate_alert_dict(d: Dict[str, Any]) -> Alert:
    """
    Normalize keys and validate with Pydantic, but do not explode on extras.
    Convert common aliases manually too.
    """
    # Normalize some common alias keys manually (if not using Field aliases)
    # Examples only; you can extend this map if needed.
    if "ticker" in d and "symbol" not in d:
        d["symbol"] = d["ticker"]
    if "side" in d and "action" not in d:
        d["action"] = d["side"]
    if "close" in d and "price" not in d:
        d["price"] = d["close"]
    if "quantity" in d and "qty" not in d:
        d["qty"] = d["quantity"]

    # Prefer Pydantic v2 .model_validate, fall back to v1 .parse_obj
    if hasattr(Alert, "model_validate"):
        return Alert.model_validate(d)  # type: ignore[attr-defined]
    else:
        return Alert.parse_obj(d)       # Pydantic v1

# ------------------------------------------------------------------------------
# Webhook endpoint
# ------------------------------------------------------------------------------
@app.post("/webhook")
async def webhook(request: Request):
    payload = await _extract_payload(request)

    # If you expect at least one of these fields, check and return 400 (not 422)
    if not any(k in payload for k in ("symbol", "ticker", "action", "side", "price", "close")):
        raise HTTPException(
            status_code=400,
            detail="Payload missing trading fields. Provide at least symbol/ticker and action/side."
        )

    alert: Alert
    try:
        alert = _validate_alert_dict(payload)
    except Exception as e:
        # Avoid 422; give a 400 with the reason and log details
        logger.exception("Alert validation failed")
        raise HTTPException(status_code=400, detail=f"Invalid alert payload: {e}")

    # Example: minimal normalized dict you can use downstream
    normalized: Dict[str, Any] = {
        "symbol": alert.symbol,
        "action": (alert.action.lower() if alert.action else None),
        "price": alert.price,
        "qty": alert.qty,
        "comment": alert.comment
    }

    # Sanity checks you control; 400 if business rules fail
    if not normalized["symbol"]:
        raise HTTPException(status_code=400, detail="Missing symbol/ticker")
    if normalized["action"] not in (None, "buy", "sell"):  # allow None if you handle it later
        raise HTTPException(status_code=400, detail="action/side must be 'buy' or 'sell'")

    # TODO: forward to Capital.com or your trade router here.
    # Example placeholder:
    # result = place_order(normalized)  # make sure to catch and surface upstream errors as 400/502 etc.

    logger.info(f"[webhook] normalized={normalized}")
    return {"ok": True, "received": normalized}
