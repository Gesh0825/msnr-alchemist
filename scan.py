#!/usr/bin/env python3
"""
MSNR - Alchemist scanner.  Runs on a schedule, writes docs/data.json.

Detects, exactly as the source documents define them:
  H1 OCL      3 consecutive same-colour H1 candles -> level at the previous close
  M15 SNR     bodies only: Classic A (bull close -> bear open), Classic V
  SBR / RBS   broken support becomes resistance / broken resistance becomes support
  Strong zone an H1 OCL with a 15m SBR or RBS sitting on it

It publishes levels and setups. It publishes NO performance figures,
because none of the stop/target pairs tested profitable.
"""
import os, json, sys, datetime as dt, urllib.request, urllib.parse

SYMBOL     = os.environ.get("MSNR_SYMBOL", "XAU/USD")
RISK_USD   = float(os.environ.get("MSNR_RISK", "100"))
SL_USD     = float(os.environ.get("MSNR_SL", "3"))
TP_USD     = float(os.environ.get("MSNR_TP", "6"))
CONTRACT   = float(os.environ.get("MSNR_CONTRACT", "100"))   # XAUUSD = 100 oz
CO_TOL     = float(os.environ.get("MSNR_TOL", "1.0"))
H1_RUN     = int(os.environ.get("MSNR_H1RUN", "3"))
REARM_BARS = int(os.environ.get("MSNR_REARM", "96"))
EXPIRE_BARS= int(os.environ.get("MSNR_EXPIRE", "96"))
ALERT_DIST = float(os.environ.get("MSNR_ALERT_DIST", "5"))   # only ping if the entry is this close to price
KEEP       = int(os.environ.get("MSNR_KEEP", "80"))
MAX_SETUPS = int(os.environ.get("MSNR_MAX_SETUPS", "8"))

# ---------------------------------------------------------------- feed
# THE ONLY PLACE THE DATA SOURCE APPEARS. Swap this one function to change feed.
def fetch_m15(n=3000):
    key = os.environ.get("TWELVEDATA_KEY", "")
    if not key:
        raise SystemExit("TWELVEDATA_KEY is not set")
    q = urllib.parse.urlencode({
        "symbol": SYMBOL, "interval": "15min", "outputsize": min(n, 5000),
        "order": "ASC", "timezone": "UTC", "apikey": key})
    url = "https://api.twelvedata.com/time_series?" + q
    with urllib.request.urlopen(url, timeout=45) as r:
        j = json.loads(r.read().decode())
    if j.get("status") != "ok" or "values" not in j:
        raise SystemExit("feed error: " + json.dumps(j)[:400])
    out = []
    for v in j["values"]:
        out.append({
            "t": v["datetime"],
            "o": float(v["open"]), "h": float(v["high"]),
            "l": float(v["low"]),  "c": float(v["close"])})
    out = tradeable(out)
    if len(out) < 200:
        raise SystemExit(f"feed returned only {len(out)} tradeable bars")
    return out

def tradeable(bars):
    """The feed emits flat filler candles while the market is shut. They are not real
       price action - left in, they invent Classic A/V levels and fake SBR/RBS flips.
       Dropping them also makes the series match an MT5 chart, which has no weekend bars."""
    out = []
    for b in bars:
        t = dt.datetime.strptime(b["t"], "%Y-%m-%d %H:%M:%S")
        wd = t.weekday()                       # 0 Mon .. 5 Sat .. 6 Sun
        if wd == 5: continue                   # Saturday
        if wd == 4 and t.hour >= 21: continue  # after the Friday close
        if wd == 6 and t.hour < 22: continue   # before the Sunday open
        if (b["h"] - b["l"]) < 0.02: continue  # dead filler candle
        out.append(b)
    return out

def bar_age_minutes(bar_t):
    t = dt.datetime.strptime(bar_t, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)
    return (dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 60.0

# ------------------------------------------------------- MSNR detection
def hour_key(ts):  return ts[:13]

def build_h1(m):
    """derive H1 from M15 so both series can never disagree"""
    h, cur, key = [], None, None
    for i, b in enumerate(m):
        k = hour_key(b["t"])
        if k != key:
            if cur: h.append(cur)
            cur = {"o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "end": i}
            key = k
        else:
            cur["h"] = max(cur["h"], b["h"]); cur["l"] = min(cur["l"], b["l"])
            cur["c"] = b["c"]; cur["end"] = i
    if cur: h.append(cur)
    return h

def scan(m):
    h = build_h1(m)
    bull_h = [x["c"] > x["o"] for x in h]
    ocl = []                                  # (m15_index_known_at, price, is_support)
    for k in range(H1_RUN - 1, len(h)):
        seg = bull_h[k - H1_RUN + 1:k + 1]
        if all(seg) or not any(seg):
            ocl.append((h[k]["end"], h[k - 1]["c"], bull_h[k]))

    sup, res = [], []            # each entry [price, kind]  kind 1 classic, 3 flip
    live, oi = [], 0
    seen, armed, fresh = {}, [], []
    N = len(m)
    last = N - 2                 # last CLOSED bar (the newest bar may be forming)
    bull = [b["c"] > b["o"] for b in m]

    for i in range(2, last + 1):
        while oi < len(ocl) and ocl[oi][0] <= i:
            live.append((ocl[oi][1], ocl[oi][2])); oi += 1
        live = live[-50:]

        if bull[i-1] and not bull[i]: res.append([m[i-1]["c"], 1])
        if not bull[i-1] and bull[i]: sup.append([m[i-1]["c"], 1])

        keep = []
        for lv in sup:
            if m[i]["c"] < lv[0] <= m[i-1]["c"]: res.append([lv[0], 3])
            else: keep.append(lv)
        sup = keep[-KEEP:]
        keep = []
        for lv in res:
            if m[i]["c"] > lv[0] >= m[i-1]["c"]: sup.append([lv[0], 3])
            else: keep.append(lv)
        res = keep[-KEEP:]

        for (op, is_sup) in live:
            pool = sup if is_sup else res
            match = next((lv for lv in reversed(pool)
                          if lv[1] == 3 and abs(lv[0] - op) <= CO_TOL), None)
            if match is None: continue
            if is_sup and not op < m[i]["l"]: continue
            if not is_sup and not op > m[i]["h"]: continue
            d = 1 if is_sup else -1
            key = (round(op, 1), d)
            if key in seen and i - seen[key] < REARM_BARS: continue
            seen[key] = i
            z = mk_setup(op, d, m[i]["t"], i)
            z["dist_at_arm"] = round(abs(op - m[i]["c"]), 2)
            armed.append(z)
            if i == last and z["dist_at_arm"] <= ALERT_DIST: fresh.append(z)

    price = m[-1]["c"]
    age = bar_age_minutes(m[last]["t"])
    closed = age > 90
    live_setups = [a for a in armed if last - a["_bar"] <= EXPIRE_BARS]
    for a in armed: a.pop("_bar", None)
    return {
        "symbol": SYMBOL,
        "price": round(price, 2),
        "bar_time": m[last]["t"],
        "bar_age_min": round(age, 1),
        "market_closed": closed,
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
        "setups": live_setups[-MAX_SETUPS:],
        "new": fresh,
        "levels": levels_near(sup, res, live, price),
        "params": {"sl": SL_USD, "tp": TP_USD, "risk": RISK_USD, "tol": CO_TOL,
                   "alert_dist": ALERT_DIST, "keep": KEEP},
    }

def mk_setup(op, d, t, bar):
    lots = round(RISK_USD / (SL_USD * CONTRACT), 2)
    return {
        "_bar": bar,
        "side": "BUY" if d > 0 else "SELL",
        "type": ("RBS retest at H1 OCL" if d > 0 else "SBR retest at H1 OCL"),
        "entry": round(op, 2),
        "sl": round(op - SL_USD if d > 0 else op + SL_USD, 2),
        "tp": round(op + TP_USD if d > 0 else op - TP_USD, 2),
        "lots": lots,
        "time": t,
    }

def levels_near(sup, res, live, price):
    out = []
    for lv in sup[::-1]:
        if lv[1] == 3: out.append({"price": round(lv[0], 2), "kind": "RBS", "side": "support"})
        if len(out) >= 6: break
    n = 0
    for lv in res[::-1]:
        if lv[1] == 3:
            out.append({"price": round(lv[0], 2), "kind": "SBR", "side": "resistance"}); n += 1
        if n >= 6: break
    for (op, is_sup) in live[-4:]:
        out.append({"price": round(op, 2), "kind": "OCL 1H",
                    "side": "support" if is_sup else "resistance"})
    for o in out: o["dist"] = round(o["price"] - price, 2)
    out.sort(key=lambda x: -x["price"])
    return out

# ---------------------------------------------------------------- notify
def notify(text):
    tok = os.environ.get("TELEGRAM_TOKEN", "")
    cid = os.environ.get("TELEGRAM_CHAT_ID", "")
    if tok and cid:
        body = urllib.parse.urlencode({"chat_id": cid, "text": text}).encode()
        try:
            urllib.request.urlopen(
                f"https://api.telegram.org/bot{tok}/sendMessage", data=body, timeout=20).read()
            print("telegram sent")
        except Exception as e:
            print("telegram failed:", e)
    sub = os.environ.get("PUSH_SUBSCRIPTION", "")
    vap = os.environ.get("VAPID_PRIVATE_KEY", "")
    if sub and vap:
        try:
            from pywebpush import webpush
            webpush(subscription_info=json.loads(sub),
                    data=json.dumps({"title": "MSNR signal", "body": text}),
                    vapid_private_key=vap,
                    vapid_claims={"sub": os.environ.get("VAPID_EMAIL", "mailto:none@example.com")})
            print("web push sent")
        except Exception as e:
            print("web push failed:", e)

def main():
    m = fetch_m15()
    data = scan(m)
      with open(data.json", "w") as f:
        json.dump(data, f, indent=1)
    print(f"{data['bar_time']}  price {data['price']}  "
          f"setups {len(data['setups'])}  new {len(data['new'])}")
    if data["market_closed"]:
        print(f"market looks shut - newest bar is {data['bar_age_min']:.0f} min old. No alerts.")
        return
    for s in data["new"]:
        notify(f"MSNR  {s['side']} LIMIT {s['entry']}\n"
               f"SL {s['sl']}   TP {s['tp']}\n{s['lots']} lots\n{s['type']}")

if __name__ == "__main__":
    main()
