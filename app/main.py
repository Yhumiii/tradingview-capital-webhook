# app/main.py
import os
import json
import re
import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.schemas import TradingViewAlert
from app import capital_client as cap

APP_SECRET = os.getenv("WEBHOOK_SECRET", "")
PATH_TOKEN = os.getenv("WEBHOOK_TOKEN")

app = FastAPI()
logger = logging.getLogger("uvicorn.error")


@app.get("/health")
def health():
    return {"status": "ok"}


def _parse_text_body_to_dict(text: str) -> Dict[str, Any]:
    """
    Parse simple key=value or key: value lines from a text/plain body.
    Returns {} if nothing meaningful is found.
    """
    data: Dict[str, Any] = {}
    for line in text.splitlines():
        m = re.match(r"\s*([A-Za-z0-9_\-\.]+)\s*[:=]\s*(.+?)\s*$", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2)
        # Try numeric cast
        try:
            if re.match(r"^-?\d+(\.\d+)?$", v):
                v = float(v)
        except Exception:
            pass
        data[k] = v
    return data


async def _extract_payload(request: Request) -> Dict[str, Any]:
    """
    Robustly extract a dict payload:
    - Try JSON first (even if content-type is text/plain).
    - Else parse key/value text lines.
    - Else wrap as {"raw": "..."}.
    """
    raw_bytes = await request.body()
    raw_str = raw_bytes.decode("utf-8", errors="replace")
    ctype = request.headers.get("content-type", "")

    logger.info(f"[webhook] content-type={ctype}")
    logger.info(f"[webhook] raw (first 500B)={raw_str[:500]}")

    # JSON attempt
    try:
        return json.loads(raw_str)
    except Exception:
        pass

    # text/plain salvage
    kv = _parse_text_body_to_dict(raw_str)
    if kv:
        return kv

    # last resort
    return {"raw": raw_str}


def _normalize_aliases(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map common TradingView aliases into our model field names.
    Does not delete original keys.
    """
    if "ticker" in d and "symbol" not in d:
        d["symbol"] = d["ticker"]
    if "side" in d and "action" not in d:
        d["action"] = d["side"]
    if "close" in d and "price" not in d:
        d["price"] = d["close"]
    if "quantity" in d and "qty" not in d:
        d["qty"] = d["quantity"]
    if "stop_loss_pct" in d and "sl_pct" not in d:
        d["sl_pct"] = d["stop_loss_pct"]
    return d


def _validate_alert_dict(d: Dict[str, Any]) -> TradingViewAlert:
    """
    Validate using the (now relaxed) Pydantic model.
    Works with Pydantic v1 or v2.
    """
    d = _normalize_aliases(d)
    if hasattr(TradingViewAlert, "model_validate"):  # pydantic v2
        return TradingViewAlert.model_validate(d)  # type: ignore[attr-defined]
    else:  # pydantic v1
        return TradingViewAlert.parse_obj(d)


@app.post("/webhook/{token}")
async def webhook(
    token: str,
    request: Request,
    content_type: str = Header(default="")
):
    # --- Basic path token check (same as before) ---
    if PATH_TOKEN and token != PATH_TOKEN:
        raise HTTPException(status_code=401, detail="invalid token")

    # --- Extract payload robustly (prevents FastAPI 422) ---
    payload = await _extract_payload(request)

    # Quick sanity: require a
