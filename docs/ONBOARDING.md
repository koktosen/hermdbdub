# Onboarding — how a new wall gets set up

The goal: a person plugs an SD card into their computer, answers a handful of plain questions, and the wall appears
on their TV. Their Hermes agent fills in whatever it already knows; the browser asks for the rest; nobody edits YAML.

## What the person genuinely has to provide
Everything else is derived or defaulted.

| ask | why | who can answer |
|---|---|---|
| which Pi / mini PC | picks the OS image (32-bit for Pi 1/2, 64-bit for 3+) and kiosk tweaks | person (or a photo of the board) |
| a name and login for the Pi | hostname, SSH user | person; agent can suggest |
| Wi-Fi name + password | first boot without a cable | person |
| Tailscale or Headscale, and its login server | the wall must reach the server from anywhere | agent usually knows |
| the city they live in | weather + timezone (geocoded for them) | agent usually knows |
| what they want to see | pages, tiles, feeds, tickers | conversation; agent proposes |
| calendar links | secret addresses live behind their logins — nobody can fetch them | person, with per-provider click-paths shown |
| backdrops | generated for their city by the agent, uploaded by them, or none | choice |
| X (optional) | developer app + browser login | person, walkthrough |

Three moments need a human and always will: inserting the SD card into the Pi, approving the Pi into the tailnet,
and the browser login for X.

## The setup page — `http://<server>:8470/setup`
A single friendly page served by the dashboard itself. It says what the wall is and how it works, in one paragraph,
and then walks through the questions above as cards. Honest notes where they matter ("to use it away from home the
wall needs a connection to your computer — that is what the tailnet is for"). Every field shows whether it was
**filled by your agent**, **filled by you**, or **still needed**.

- `GET /api/setup` — current answers (secrets redacted); the agent reads this to see what is missing.
- `POST /api/setup` — save answers, partial is fine; the agent and the browser both use it.
- `POST /api/setup/validate` — test a calendar link right when it is pasted ("Work: 9 events in the next 14 days").
- `POST /api/setup/apply` — write `config.yaml` from the answers and run the collectors.
- `GET /api/setup/cloudinit` — the two first-boot files generated from the answers, plus the exact flash command.

Finishing the page produces the human checklist: flash command, "put the card in the Pi", the bootstrap line,
the tailnet approval link, and — if chosen — "your agent is generating backdrops for <city>".

## The agent's part (skill `wall-brief`, "Setup" section)
1. Read `GET /api/setup`. For each empty field it is confident about (city, tailnet, the owner's name, which agent
   voice it uses, what the owner has said they care about), `POST` it. Never guess Wi-Fi passwords or calendar links.
2. Tell the owner the page URL and which cards still need them.
3. When the owner picks "generate backdrops for my city": produce the 13 images (fallback + 6 conditions × day/night)
   with the agent's image tool into `server/web/img/weather/` and `server/web/img/location.jpg`.
4. After "apply": run the doctor checks and report.

## The walkthrough (no agent)
The same page, with each step's commands shown to copy and paste. Nothing is hidden behind the agent.

## Built: `server/bin/hermdbw` (flash · adopt · doctor)
See the root README. Design notes that still apply:
- `hermdbw flash` — detect the removable card (refuse non-removable disks), fetch + verify the right image, write it,
  drop the generated cloud-init files on it.
- `hermdbw adopt` — wait for the Pi to appear, install the SSH key, run the bootstrap remotely, join the tailnet,
  re-point the kiosk.
- `hermdbw doctor` — every link in the chain, named in plain words when it fails.
