# hermdbw server

The server side: collectors that fetch everything, a static web page, and a tiny HTTP server. Runs on any Linux box
with Python 3.11+ (not on the display Pi). Index: [`../README.md`](../README.md) · Pi: [`../pi/README.md`](../pi/README.md) · Agent: [`../hermes/README.md`](../hermes/README.md)

## Demo mode
`python3 bin/demo-data.py <dir>` writes a full set of fictional `*.json`; `HERMDBW_DATA=<dir> PORT=8471 python3 serve.py` serves the page against it. Used for the screenshots and for previewing layout changes without touching live data.

## Install / operate
```bash
bash install.sh                       # idempotent: venv, config.yaml (from the example), systemd --user units, wallctl. Re-run after git pull.
systemctl --user status hermdbw-web hermdbw-collect.timer hermdbw-ops.timer hermdbw-xapi.timer
journalctl --user -u hermdbw-collect -n 50
curl -s localhost:8470/healthz | jq .collectors   # per-collector ok / error
cd collectors && ../.venv/bin/python run_all.py   # run everything now; exit 1 if any collector failed
```
Units (all `systemd --user`, so `loginctl enable-linger` is set by the installer):

| unit | what | cadence |
|---|---|---|
| `hermdbw-web.service` | `serve.py` on `0.0.0.0:8470` (set `PORT=` to change) | always |
| `hermdbw-collect.timer` | calendar, weather, brief, markets, rss, xtrends, fng | every 5 min |
| `hermdbw-ops.timer` | host status | every 1 min |
| `hermdbw-xapi.timer` | X API (trends / mentions / usage) | at `x_api.times` |

## Collectors → `data/*.json`

| collector | source | output |
|---|---|---|
| `cal_feeds.py` | every `calendars[].url` (iCal/ICS/webcal), recurrences expanded for `calendar_days` | `calendar.json` |
| `weather.py` | Open-Meteo (no key): current, 24 h hourly, 7-day | `weather.json` |
| `markets.py` | CoinGecko (crypto + 7-day sparkline, logos cached to `web/logos/`), Yahoo Finance chart endpoint (stocks) | `markets.json` |
| `fng.py` | alternative.me crypto Fear & Greed | `fng.json` |
| `rss.py` | `rss_feeds[]` via feedparser | `rss.json` |
| `brief.py` | newest `## Response` from `~/.hermes/cron/output/<hermes_brief_job>/`, plus `brief.mp3` via Piper when the text changes | `brief.json`, `brief.mp3` |
| `xapi.py` | X API through `xurl`: personalized trends, optional mentions/timeline, X's own usage count; every request logged to `x_usage.jsonl` | `xtrends.json`, `xme.json`, `xusage.json` |
| `xtrends.py` | Hermes cron output for X trends — only when `x_api.trends` is off | `xtrends.json` |
| `ops.py` | load/mem, AMD GPUs via sysfs, ComfyUI queues, `systemctl --user` services, Tailscale peers, disks, newest build artifact, Moonraker printer | `ops.json` |
| `run_all.py` | runs the above by name; writes `status.json` (per-collector ok/error + the layout config the page reads) | `status.json` |

One failing source never blanks the wall: errors land in the JSON and in the page footer.

## HTTP endpoints (`serve.py`)

| | |
|---|---|
| `GET /` | the page; `?page=feed`, `?rotate=0` (seconds; overrides config), `?takeover=1` (open the brief overlay silently), `?debug=1` |
| `GET /data/<name>.json`, `/data/brief.mp3` | collector output, `Cache-Control: no-store` |
| `GET /healthz` | = `status.json` |
| `GET\|POST /api/trigger?what=brief\|dismiss` | start / stop the full-screen brief; the page polls every 5 s |
| `POST /api/alert` JSON `{title, body?, image?, level?: info\|warn\|urgent, ttl_minutes?, flash_seconds?}` | flash alert; `GET /api/alert` lists, `?dismiss=ID`, `?clear=1` |

Images for alerts go under `web/img/alerts/` and are referenced as `img/alerts/<file>`.

## Configuration

`config.yaml` (mode 600, gitignored). Every key is documented inline in [`config.yaml.example`](config.yaml.example).
Edit by hand, or with `bin/wallctl` (installed to `~/.local/bin`), which validates each change by re-running the affected
collector and prints `OK …` or `FAILED …`:
```
wallctl show [--full]                 wallctl calendar add "Name" "URL" [--color #hex] | calendar remove "Name"
wallctl rss add "Name" "URL"          wallctl stocks set SYM …            wallctl crypto set <coingecko-id> …
wallctl location set LAT LON --name X wallctl set rotate_seconds 45       wallctl refresh [collector…]
wallctl xusage                        # exact X API request count by day + X's own monthly number
```
`wallctl` uses ruamel.yaml so your comments survive. Secret URLs are redacted in `show` unless `--full`.

## Weather backdrops
`web/img/weather/<clear|partly|overcast|fog|rain|storm>-<day|night>.jpg` are chosen automatically from the current
weather code and daylight; `location.image` is the fallback. The repo ships only the fallback. Generate your own set
with any image tool (the originals here were made locally with ComfyUI from a prompt describing the city under each sky).

## Gotchas we hit
- Don't name a collector `calendar.py` — it shadows the stdlib module `requests` depends on.
- feedparser's `*_parsed` structs are UTC: convert with `calendar.timegm`, not `time.mktime`.
- YouTube's channel RSS started returning 404 for most channels (2026-10), so there is no YouTube column; the Data API is the robust route if you want one.
- A grid/flex box won't shrink below its content: the 24 h chart box needs `min-width: 0` or it can never redraw smaller.
- The whole board scales via the root `font-size: calc(22 * 100vw / 1920)`; use rem, not px, for anything new.
