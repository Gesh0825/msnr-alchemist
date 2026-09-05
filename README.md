# MSNR - Alchemist  (web app + scheduled scanner)

Marks the levels the MSNR documents define and pings your phone when a setup forms.
It shows **no win rate and no P&L**, because none was demonstrated: every stop/target
pair tested came out flat or negative on 2022-2026 XAUUSD M15. Use it to know where
to look, not as a signal to follow blindly.

## What it detects
* **H1 OCL** - 3 consecutive same-colour H1 candles, level at the previous candle's close
* **M15 SNR** - bodies only. Classic A (bull close -> bear open), Classic V
* **SBR / RBS** - broken support becomes resistance, broken resistance becomes support
* **Strong zone** - an H1 OCL with a 15m SBR or RBS sitting on it (within `MSNR_TOL`)

## Setup

1. **Check the feed works.** Free key at twelvedata.com, then open in a browser:
   `https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=15min&outputsize=5&apikey=YOUR_KEY`
   If that returns candles, continue. If it returns a plan error, gold is not on the free
   tier and the feed has to change (only `fetch_m15()` in `scan.py` needs replacing).

2. **New GitHub repo**, push these files.

3. **Settings -> Pages** -> Source: *Deploy from a branch*, branch `main`, folder `/docs`.
   Your app is at `https://<you>.github.io/<repo>/`

4. **Settings -> Secrets and variables -> Actions**, add:
   * `TWELVEDATA_KEY` - required
   * Easiest alerts: `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` (make a bot with @BotFather,
     get your chat id from @userinfobot). Works on iPhone with no extra setup.
   * Or web push: `VAPID_PRIVATE_KEY`, `VAPID_EMAIL`, `PUSH_SUBSCRIPTION` (see below)

5. **Actions tab** -> enable workflows -> run *MSNR scan* once by hand to confirm it works.

## Web push on iPhone (optional - Telegram is simpler)
1. Generate VAPID keys: `python -c "from py_vapid import Vapid01 as V; v=V(); v.generate_keys(); print(v.public_key_urlsafe_base64(), v.private_key_urlsafe_base64())"`
2. Paste the public key into `VAPID_PUBLIC` at the top of `docs/index.html`, push.
3. On the iPhone open the page in Safari -> Share -> **Add to Home Screen**.
4. Open it from the icon, press *Enable push alerts*, copy the JSON it shows.
5. Save that JSON as the GitHub secret `PUSH_SUBSCRIPTION`, and the private key as
   `VAPID_PRIVATE_KEY`.

## Settings (workflow env, or repo variables)
| name | default | meaning |
|---|---|---|
| `MSNR_SL` | 3 | stop, $ from entry - **not from the documents, and not proven** |
| `MSNR_TP` | 6 | target, $ from entry - same caveat |
| `MSNR_RISK` | 100 | risk per trade, $ (drives lot size) |
| `MSNR_ALERT_DIST` | 5 | only ping if the entry is this close to price. $5 ~ 1.6 alerts/day |
| `MSNR_TOL` | 1.0 | how close a 15m SNR must be to the H1 OCL to count as one zone |
| `MSNR_KEEP` | 80 | SNR levels kept per side. Higher = more zones = more alerts |
| `MSNR_H1RUN` | 3 | consecutive same-colour H1 candles needed to mark an OCL |

## Known limits
* GitHub's scheduler can run late under load, so a signal may arrive a few minutes
  after the M15 close. For a limit order resting 24h that is usually fine.
* Twelve Data's prices are not your broker's. Levels can sit a dollar or two off your
  MT5 chart. If that matters, swap `fetch_m15()` for a MetaAPI call.
* Free tier is 800 requests/day. This uses 96.
