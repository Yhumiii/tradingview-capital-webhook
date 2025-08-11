# app/main.py
import os
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from app.schemas import TradingViewAlert
from app import capital_client as cap

APP_SECRET = os.getenv("WEBHOOK_SECRET", "")  # shared secret to validate webhook
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/webhook/{token}")
async def webhook(token: str, alert: TradingViewAlert, request: Request, content_type: str = Header(default="")):
    # Basic auth: path token + optional secret in body
    if token != os.getenv("WEBHOOK_TOKEN"):
        raise HTTPException(status_code=401, detail="invalid token")
    if APP_SECRET and alert.secret != APP_SECRET:
        raise HTTPException(status_code=401, detail="invalid secret")

    # Make sure we are logged in (refresh if needed)
    try:
        cap.login()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"capital.com auth failed: {e}")

    # Map TV symbol to Capital epic. If you already know the epic, send it directly in TradingView JSON.
    epic = alert.symbol  # e.g., "AAPL" or Capital's epic like "US.AAPL" depending on your mapping

    direction = "BUY" if alert.side == "buy" else "SELL"
    try:
        confirm = cap.place_market_position(
            epic=epic,
            direction=direction,
            size=alert.qty,
            stop_loss=alert.stop_loss,
            take_profit=alert.take_profit
        )
        return JSONResponse({"status": "ok", "confirm": confirm})
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"order failed: {e}")
# (Paste the main.py code from the tutorial here)
