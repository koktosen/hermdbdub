"""Crypto (CoinGecko, 7-day sparkline) + stocks (Yahoo Finance chart endpoint). No API keys."""
import requests

from pathlib import Path

from common import ROOT, load_config, write_json

LOGOS = ROOT / "web" / "logos"

UA = {"User-Agent": "Mozilla/5.0 rpi-dashboard/1.0"}


def crypto(ids: list) -> list:
    if not ids:
        return []
    r = requests.get("https://api.coingecko.com/api/v3/coins/markets", timeout=20, headers=UA, params={
        "vs_currency": "usd", "ids": ",".join(ids), "sparkline": "true", "price_change_percentage": "24h"})
    r.raise_for_status()
    by_id = {c["id"]: c for c in r.json()}
    out = []
    for i in ids:  # keep config order
        c = by_id.get(i)
        if not c:
            continue
        spark = c.get("sparkline_in_7d", {}).get("price") or []
        out.append({"symbol": c["symbol"].upper(), "name": c["name"], "price": c["current_price"], "logo": logo(c),
                    "change_24h": round(c.get("price_change_percentage_24h") or 0, 2),
                    "spark": [round(p, 6) for p in spark[::4]]})  # 168 hourly points → 42
    return out


def logo(c: dict) -> str | None:
    """Cache the CoinGecko logo once under web/logos/ so the kiosk never hotlinks it."""
    url = c.get("image")
    if not url:
        return None
    LOGOS.mkdir(parents=True, exist_ok=True)
    dest = LOGOS / f"{c['symbol'].lower()}.png"
    if not dest.exists():
        try:
            r = requests.get(url, timeout=15, headers=UA)
            r.raise_for_status()
            dest.write_bytes(r.content)
        except Exception:
            return None
    return f"logos/{dest.name}"


def stocks(symbols: list) -> list:
    out = []
    for s in symbols:
        try:
            r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{s}", timeout=15, headers=UA,
                             params={"range": "5d", "interval": "1d"})
            res = r.json()["chart"]["result"][0]
            meta = res["meta"]
            price, prev = meta["regularMarketPrice"], meta.get("chartPreviousClose") or meta.get("previousClose")
            closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
            out.append({"symbol": s, "price": round(price, 2),
                        "change_24h": round(100 * (price - prev) / prev, 2) if prev else None,
                        "spark": [round(c, 2) for c in closes]})
        except Exception as e:
            out.append({"symbol": s, "error": f"{type(e).__name__}"})
    return out


def movers(n: int = 10) -> dict:
    """Yahoo's predefined day-gainers / day-losers screens (US equities, price >= $5, real volume). Feeds the tape."""
    out = {}
    for side, scr in (("up", "day_gainers"), ("down", "day_losers")):
        try:
            r = requests.get("https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved", timeout=15,
                             headers=UA, params={"scrIds": scr, "count": n})
            quotes = r.json()["finance"]["result"][0]["quotes"]
            out[side] = [{"symbol": q["symbol"], "name": (q.get("shortName") or q.get("longName") or "")[:40],
                          "price": round(q["regularMarketPrice"], 2), "change_24h": round(q["regularMarketChangePercent"], 2)}
                         for q in quotes if q.get("regularMarketPrice") is not None][:n]
        except Exception as e:
            out[side] = []; out["error"] = f"{type(e).__name__}"
    return out


def main() -> None:
    m = load_config().get("markets") or {}
    write_json("markets", {"crypto": crypto(m.get("crypto", [])), "stocks": stocks(m.get("stocks", [])),
                           "movers": movers(int(m.get("movers", 10)))})


if __name__ == "__main__":
    main()
