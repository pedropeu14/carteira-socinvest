"""Fetch daily closes from Yahoo Finance for every position in positions.json
and write data/prices.json (consumed by index.html).

Stdlib only. Run locally or in CI:
  python fetch_prices.py
"""
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHART_URL = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
             "?period1={p1}&period2={p2}&interval=1d&events=div")
HEADERS = {"User-Agent": "Mozilla/5.0 (carteira-socinvest)"}
PAUSE = 0.35
RETRIES = 3


def load_positions():
    with open(os.path.join(BASE_DIR, "positions.json"), encoding="utf-8") as f:
        return json.load(f)


def load_ledger():
    try:
        with open(os.path.join(BASE_DIR, "ledger.json"), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def fetch_chart(symbol, p1, p2, adjusted=False):
    """adjusted=True devolve o close ajustado por proventos (retorno total) —
    usado no benchmark, que precisa ser comparavel ao NAV real da conta."""
    url = CHART_URL.format(sym=urllib.parse.quote(symbol), p1=p1, p2=p2)
    last_err = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            result = data["chart"]["result"][0]
            meta = result["meta"]
            ts = result.get("timestamp") or []
            closes = result["indicators"]["quote"][0].get("close") or []
            if adjusted:
                adj = ((result["indicators"].get("adjclose") or [{}])[0]).get("adjclose")
                if adj:
                    closes = adj
                else:
                    print(f"WARN {symbol}: sem adjclose, usando close cru")
            dedup = {}
            for t, c in zip(ts, closes):
                if c is None:
                    continue
                d = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
                dedup[d] = round(float(c), 6)  # last quote of the day wins
            if not dedup and meta.get("regularMarketPrice") is not None:
                # thin listings (e.g. PJAG.SG) expose only a live quote
                t = meta.get("regularMarketTime") or time.time()
                d = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
                dedup[d] = round(float(meta["regularMarketPrice"]), 6)
            dates = sorted(dedup)
            vals = [dedup[d] for d in dates]
            return {
                "currency": meta.get("currency"),
                "dates": dates,
                "closes": vals,
                "last": vals[-1] if vals else None,
                "last_date": dates[-1] if dates else None,
            }
        except Exception as e:  # noqa: BLE001 - retry then report
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    return {"error": f"{type(last_err).__name__}: {last_err}"}


def main():
    book = load_positions()
    inception = datetime.strptime(book["meta"]["inception_date"], "%Y-%m-%d")
    p1 = int((inception - timedelta(days=7)).replace(tzinfo=timezone.utc).timestamp())
    p2 = int(time.time()) + 86400

    symbols = [p["symbol"] for p in book["positions"]]
    # posicoes ja' encerradas: sem serie delas o NAV historico fica furado
    for c in load_ledger().get("closed", []):
        if c["symbol"] not in symbols:
            symbols.append(c["symbol"])
    bench = (book["meta"].get("benchmark") or {}).get("symbol")
    if bench and bench not in symbols:
        symbols.append(bench)   # benchmark: nao e' posicao, mas precisa da serie
    out = {"updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
           "series": {}}
    errors = []

    def grab(sym):
        res = fetch_chart(sym, p1, p2, adjusted=(sym == bench))
        out["series"][sym] = res
        if "error" in res:
            errors.append(f"{sym}: {res['error']}")
            print(f"WARN {sym}: {res['error']}")
        else:
            print(f"ok   {sym:12s} {res['currency']} {res['last']} ({res['last_date']}, {len(res['dates'])} closes)")
        time.sleep(PAUSE)

    for sym in symbols:
        grab(sym)

    # câmbio p/ USD de toda moeda de cotação encontrada (GBp = pence -> GBP)
    ccys = {("GBP" if r.get("currency") == "GBp" else r.get("currency"))
            for r in out["series"].values()} - {None, "USD"}
    for ccy in sorted(ccys):
        symbols.append(f"{ccy}USD=X")
        grab(f"{ccy}USD=X")

    os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
    path = os.path.join(BASE_DIR, "data", "prices.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"\nwrote {path} ({len(symbols)} symbols, {len(errors)} errors)")
    if errors and len(errors) > len(symbols) // 4:
        # fail CI only when the refresh is broadly broken; one flaky fund NAV
        # should not block the daily update (dashboard falls back per-symbol)
        raise SystemExit("too many fetch errors: " + "; ".join(errors))


if __name__ == "__main__":
    main()
