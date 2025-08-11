from fastapi import FastAPI, Header, HTTPException

app = FastAPI()
WEBHOOK_SECRET = "PHOEBUS"

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/webhook")
def webhook(x_webhook_secret: str | None = Header(None), payload: dict = {}):
    if x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="bad secret")
    # TODO: process TradingView alert in `payload`
    return {"received": True}
