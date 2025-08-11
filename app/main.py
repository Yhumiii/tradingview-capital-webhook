# app/main.py
import os
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from app.schemas import TradingViewAlert
from app import capital_client as cap

# Optional shared secret (in body) and required path token (in URL)
APP_SECRET = os.getenv("WEBHOOK_SECRET", "")
PATH_TOKEN = os.getenv("WEBHOOK_TOKEN")

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhook/{token}")
async def webhook(
    token: str,
    alert: TradingViewAlert,
    request: Request,
    content_type: str = Header(default="")
):
    # --- Basic authentication / validation ---
    if PATH_TOKEN and token != PATH_TOKEN:
        raise HTTPException(status_code=401, detail="invalid token")
    if APP_SECRET and alert.secret != APP_SECRET:
        raise HTTPException(status_code=401, detail="invalid secret")

    # --- Ensure we have a Capital.com session ---
    try:
        cap.login()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"capital.com auth failed: {e}")

    # --- Validate required fields from alert ---
    if alert.price is None:
        raise HTTPException(status_code=400, detail="price missing in alert message")
    price = float(alert.price)

    # --- Determine quantity ---
    qty = alert.qty
    if qty is None:
        # Compute from available cash and cash_pct
        if not alert.cash_pct:
            raise HTTPException(
                status_code=400,
                detail="either qty or cash_pct must be provided"
            )
        try:
            available = cap.pick_available_account_available()
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"failed to get account balance: {e}"
            )
        notional = max(0.0, float(available)) * float(alert.cash_pct)
        if notional <= 0:
            raise HTTPException(
                status_code=400,
                detail="computed notional is 0; check cash_pct and available balance"
            )
        # Simple sizing: notional / price (instrument min size/step may require extra rounding)
        qty = notional / price
        qty = float(f"{qty:.6f}")  # mild rounding; adjust per instrument rules if needed

    # --- Direction & stop loss ---
    direction = "BUY" if alert.side.lower() == "buy" else "SELL"
    sl_pct = float(alert.sl_pct if alert.sl_pct is not None else 0.10)
    stop_level = price * (1 - sl_pct) if direction == "BUY" else price * (1 + sl_pct)

    # --- Instrument identifier (epic) ---
    # If your TradingView payload already sends a Capital.com epic, use it directly.
    epic = alert.symbol

    # --- Place order ---
    try:
        confirm = cap.place_market_position(
            epic=epic,
            direction=direction,
            size=qty,
            stop_loss=stop_level,                 # mapped to stopLevel in the client impl
            take_profit=alert.take_profit
        )
        return JSONResponse({
            "status": "ok",
            "symbol": epic,
            "direction": direction,
            "sized_qty": qty,
            "entry_price": price,
            "stop_level": stop_level,
            "confirm": confirm
        })
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"order failed: {e}")
