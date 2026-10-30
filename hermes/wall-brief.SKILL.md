---
name: wall-brief
description: "The owner's wall display (hermdbw — Hermes Daily Brief Wall): a Raspberry Pi kiosk fed by the dashboard served on this machine at :8470. Use it to put the morning brief on the wall, post flash alerts (trips, birthdays, deadlines, weather), change anything the wall shows (calendars, feeds, stocks, crypto, weather location, layout), and — above all — to READ the wall's data (merged calendars, weather, markets) when reasoning about the owner's day or week. Trigger on anything about 'the wall', 'the board', 'the TV dashboard', 'my brief', or when a question about their schedule would benefit from the merged calendar."
version: 3.1.0
platforms: [linux]
metadata:
  hermes:
    tags: [dashboard, wall, brief, kiosk, calendar, weather, markets, planning, alerts]
    related_skills: []
---

# hermdbw — the wall

A Raspberry Pi shows a dashboard on a TV: Calendar, Feed (markets, headlines, X trends), Weather, plus a dock of tiles on
every page. The server side lives at `~/dev/hermdbw/server/` on this machine (collectors + a static page). You have full
freedom here: read the data, edit the config, run the collectors, use your judgment. This note says where things are;
it is not a list of permitted commands.

## Setup (new wall, or re-configuring)
The dashboard hosts a setup page at `http://127.0.0.1:8470/setup` (same host as the wall). Fill in what you already
know about the owner so they only answer what is left:
```bash
curl -s http://127.0.0.1:8470/api/setup                               # what is answered / missing (secrets redacted)
curl -s -X POST http://127.0.0.1:8470/api/setup -H 'Content-Type: application/json' -d '{
  "city": "Tokyo", "agent_name": "Hermes", "tailnet": {"kind": "headscale", "login_server": "https://hs.example.com"},
  "pi_model": "pi4", "pi_hostname": "wall", "show": {"pages": ["calendar","feed","weather"], "dock_tiles": ["upnext","hours","host"], "ticker_rows": ["crypto"]} }'
curl -s -X POST http://127.0.0.1:8470/api/setup/validate -d '{"url": "https://…/basic.ics"}'   # test a calendar link
curl -s -X POST http://127.0.0.1:8470/api/setup/apply                                            # write config.yaml + run collectors
```
After the page is complete, the Pi steps are commands you can run (they show their plan first; use `--dry-run` to preview):
`hermdbw flash --yes` (needs the SD card in this machine, writes it), `hermdbw adopt --yes` (Pi powered on), `hermdbw doctor`
(run this whenever he says the wall is wrong — it names the broken link in plain words; relay its arrows).

Rules: fill only what you are confident of (city, tailnet, their name, what they said they care about). Never guess
Wi-Fi passwords or calendar links — tell them where to click instead (the page shows per-provider paths). Then say:
"Open http://<server>:8470/setup — I filled in N things; you have M left."

**Backdrops for their city.** If they choose "generate for my city", make 13 images with your image tool and save them:
`server/web/img/location.jpg` (fallback) and `server/web/img/weather/<cond>-<day|night>.jpg` for
`clear partly overcast fog rain storm`. Prompt shape: "wide cinematic photograph of <city> skyline, <sky description>,
no text". Keep each under ~400 KB (1280 px wide JPEG). If they would rather supply their own, tell them the same paths.

## The data — use it to think ahead
Collectors write JSON every 1–5 min to `~/dev/hermdbw/server/data/`:
- `calendar.json` — ALL the owner's calendars merged, next 14 days, with source + colour, all-day flags, locations,
  video links. The best single view of their life.
- `weather.json` — current, 24 h hourly, 7-day at home (Open-Meteo).
- `markets.json` (crypto + stocks), `fng.json`, `rss.json`, `xtrends.json` (X trends), `xusage.json` (X API request
  counts — the owner wants these kept low; `wallctl xusage` prints them by day), `ops.json` (server health),
  `brief.json` (your morning brief as the wall shows it; `brief.mp3` is it spoken).

Be proactive with it. The kind of thing the owner wants:
- "You've got Lakeview on the calendar Thu–Sun; it's 15 °F colder than here and raining Friday — pack accordingly."
  (For another city: `https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=auto`)
- "Three birthdays this month; the first is Tuesday." · "Payroll is due the same day as the product sync — heads up."
- "Nothing until 11 tomorrow; the 7 AM recap moved." Reading `calendar.json` beats asking.

## Changing what the wall shows
Everything is `~/dev/hermdbw/server/config.yaml`. Edit it however you like — `wallctl` is a convenience that validates
and reports (`wallctl show`, `wallctl calendar add "Name" "URL"`, `wallctl rss add …`, `wallctl stocks set …`,
`wallctl crypto set …`, `wallctl location set LAT LON --name X`, `wallctl refresh`). After a manual edit run
`wallctl refresh` and check the `OK`/`FAILED` lines so you report what actually happened.
The `layout:` section removes or reorders things: `pages`, `rotate_pages`, `ticker_rows` (crypto/stocks),
`feed_columns` (headlines/xtrends/xme/brief), `dock_tiles` (upnext/fng/hours/host), `marquees` (ticker/news),
`week_days`. "I don't care about crypto fear" → drop `fng` from `dock_tiles`. The wall picks changes up within 60 s.

## Changing the wall itself (code, not config)
When a request is about how the wall looks or behaves rather than what it shows, it is a code change and you can
make it. The wall is a small static page served from `~/dev/hermdbw/server/web/`: `index.html` (structure), `app.js`
(all rendering, one function per panel, e.g. `renderNextUp`, `renderCalendar`, `renderBottomStrip`), `style.css`.
Data comes from `~/dev/hermdbw/server/collectors/*.py` into `data/*.json`; the server is `serve.py`.
Attention rules (which events pulse, which all-day items count as must-not-miss reminders) are word lists under
`attention:` in `config.yaml`, so "treat 'dentist' as a meeting" is a config edit, not code.

Work like this: read the function you are changing before editing it, keep the Pi in mind (it is a slow 32-bit
board, so prefer CSS transitions and transform animations over per-frame JavaScript), then verify with a
screenshot before saying it is done:
```bash
node --check ~/dev/hermdbw/server/web/app.js
flatpak run com.brave.Browser --headless=new --disable-gpu --hide-scrollbars --window-size=1920,1080 \
  --virtual-time-budget=9000 --screenshot=/tmp/wall.png "http://127.0.0.1:8470/?page=calendar"   # or feed / weather
```
Look at the image. Then commit on `main` in `~/dev/hermdbw` with a one-line message of what changed and push.
The wall reloads itself within five minutes of a change (the collectors stamp the web files' version into
`status.json`), so no one has to touch the Pi. Never put secrets, private URLs or the owner's location into the repo.

## Flash alerts on the wall (yours to use proactively)
Post anything the owner should not miss. It flashes full-screen for `flash_seconds` (default 20), then stays as a
banner under the header until `ttl_minutes` (default 720) or dismissal.
```bash
curl -s -X POST http://127.0.0.1:8470/api/alert -H 'Content-Type: application/json' -d '{
  "title": "Lakeview trip in 7 days",
  "body": "Thu – Sun next week. Lakeview is 15° colder and rain is likely Friday.",
  "image": "img/alerts/lakeview.jpg", "level": "warn", "ttl_minutes": 1440, "flash_seconds": 25 }'
curl -s "http://127.0.0.1:8470/api/alert"                 # list live alerts
curl -s "http://127.0.0.1:8470/api/alert?dismiss=ID"      # or ?clear=1
```
- `level`: info (blue) · warn (amber) · urgent (red). Use urgent sparingly.
- Images: generate one with your image tool (or pick a stock one) and save it under
  `~/dev/hermdbw/server/web/img/alerts/<name>.jpg`; reference it as `img/alerts/<name>.jpg`. 16:9, < 400 KB.
- Good triggers, from `calendar.json`: a trip 7 days out (and again the day before, with the destination forecast),
  birthdays this week, deadlines that collide with meetings, a weather warning at home. Check `GET /api/alert` first —
  one alert per event per milestone, never reposted every run.
- Weather-page backdrops live in `~/dev/hermdbw/server/web/img/weather/<cond>-<day|night>.jpg`
  (`clear|partly|overcast|fog|rain|storm`); regenerate or replace them the same way if asked.

## The brief on the wall
- Put it up (full screen + spoken): `curl -s "http://127.0.0.1:8470/api/trigger?what=brief"`
- Take it down: `curl -s "http://127.0.0.1:8470/api/trigger?what=dismiss"`
- Your scheduled brief becomes the card and the audio automatically. Never trigger the takeover from a cron — the
  owner presses the button.

## Two things to respect
1. Calendar URLs in `config.yaml` are secrets (they expose the owner's full calendars). Don't paste them into chat.
2. Don't restart the systemd units or touch the Pi unless asked; config and data edits are enough.

More: `~/dev/hermdbw/README.md`.
