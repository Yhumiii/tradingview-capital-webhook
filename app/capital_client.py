# app/capital_client.py
import os
import time
from typing import Optional, Dict, Any
import httpx

CAPITAL_ENV = os.getenv("CAPITAL_ENV", "demo").lower()
BASE = "https://demo-api-capital.backend-capital.com" if CAPITAL_ENV == "demo" else "https://api-capital.backend-capital.com"

API_KEY = os.getenv("CAPITAL_API_KEY")           # from Capital.com Settings > API integrations
IDENTIFIER = os.getenv("CAPITAL_IDENTIFIER")     # your Capital.com login (e.g., email)
API_PASSWORD = os.getenv("CAPITAL_API_PASSWORD") # the *custom password* set for the API key
ACCOUNT_ID = os.getenv("CAPITAL_ACCOUNT_ID")     # optional: if you want to force a specific account

SESSION_HEADERS = {"X-CAP-API-KEY": API_KEY}
TOKENS: Dict[str, Optional[str]] = {"CST": None, "X-SECURITY-TOKEN": None}
LAST_AUTH = 0.0

def _auth_headers() -> Dict[str, str]:
    if not TOKENS["CST"] or not TOKENS["X-SECURITY-TOKEN"]:
        raise RuntimeError("Not authenticated")
    return {
        "CST": TOKENS["CST"],
        "X-SECURITY-TOKEN": TOKENS["X-SECURITY-TOKEN"],
    }

def login(force: bool=False):
    global LAST_AUTH
    if not force and time.time() - LAST_AUTH < 420:  # refresh proactively before 10min idle
        return

    payload = {
        "identifier": IDENTIFIER,
        "password": API_PASSWORD,
        "encryptedPassword": False
    }
    with httpx.Client(base_url=BASE, timeout=20.0) as client:
        r = client.post("/api/v1/session", headers=SESSION_HEADERS, json=payload)
        r.raise_for_status()
        TOKENS["CST"] = r.headers.get("CST")
        TOKENS["X-SECURITY-TOKEN"] = r.headers.get("X-SECURITY-TOKEN")
        LAST_AUTH = time.time()

        # (optional) switch to a specific financial account
        if ACCOUNT_ID:
            client.put("/api/v1/session", headers={**_auth_headers()}, json={"accountId": ACCOUNT_ID})

def ping():
    # keep the session alive (optional)
    with httpx.Client(base_url=BASE, timeout=10.0) as client:
        r = client.get("/api/v1/ping", headers=_auth_headers())
        r.raise_for_status()

def market_details(epic: str) -> Dict[str, Any]:
    with httpx.Client(base_url=BASE, timeout=20.0) as client:
        r = client.get(f"/api/v1/markets/{epic}", headers=_auth_headers())
        r.raise_for_status()
        return r.json()

def place_market_position(epic: str, direction: str, size: float, stop_loss: Optional[float]=None, take_profit: Optional[float]=None) -> Dict[str, Any]:
    """
    direction: 'BUY' (long) or 'SELL' (short)
    size: contract size (depends on instrument)
    """
    payload = {
        "epic": epic,
        "direction": direction.upper(),
        "size": size,
        "orderType": "MARKET",
        # You can also set "guaranteedStop": false, "forceOpen": True, etc.
    }
    if stop_loss is not None:
        payload["stopLoss"] = {"level": stop_loss}
    if take_profit is not None:
        payload["takeProfit"] = {"level": take_profit}

    with httpx.Client(base_url=BASE, timeout=30.0) as client:
        r = client.post("/api/v1/positions", headers=_auth_headers(), json=payload)
        r.raise_for_status()
        confirm_ref = r.json().get("dealReference")

        # Confirm execution status
        if confirm_ref:
            c = client.get(f"/api/v1/confirms/{confirm_ref}", headers=_auth_headers())
            c.raise_for_status()
            return c.json()
        return r.json()

def close_position(deal_id: str, direction: str, size: float) -> Dict[str, Any]:
    payload = {
        "dealId": deal_id,
        "direction": direction.upper(),  # to close, send opposite direction of the open position
        "size": size
    }
    with httpx.Client(base_url=BASE, timeout=20.0) as client:
        r = client.delete("/api/v1/positions", headers=_auth_headers(), json=payload)
        r.raise_for_status()
        return r.json()
        
def get_accounts():
    with httpx.Client(base_url=BASE, timeout=20.0) as client:
        r = client.get("/api/v1/accounts", headers=_auth_headers())
        r.raise_for_status()
        return r.json()

def pick_available_account_available() -> float:
    data = get_accounts()
    # pick current (preferred) or first; read 'balance.available'
    for acc in data.get("accounts", []):
        if acc.get("preferred"):
            return float(acc["balance"]["available"])
    if data.get("accounts"):
        return float(data["accounts"][0]["balance"]["available"])
    raise RuntimeError("No accounts returned")
