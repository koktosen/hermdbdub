# hermdbw × Hermes

What the agent adds: it reads the wall's data to think ahead for you, edits what the wall shows when you ask in chat,
writes the morning brief the wall displays and speaks, and posts flash alerts. Index: [`../README.md`](../README.md)

```bash
bash install-hermes.sh        # copies the skill to ~/.hermes/skills/wall-brief, creates two cron jobs if missing, prints their ids
```
Then set `hermes_brief_job` (and `hermes_xtrends_job`, only if you are not using the X API) in `server/config.yaml`,
and start a **new** chat session with your agent (`/new` on Telegram) so it loads the skill.

| file | purpose |
|---|---|
| `wall-brief.SKILL.md` | the skill: where the data lives (`server/data/*.json`), how to change the config (`wallctl` or direct edits), the alert and brief endpoints, and the two rules (never echo calendar URLs; don't restart units unasked) |
| `prompts/morning-brief.md` | cron prompt for the daily brief (07:30). Reads the wall's own data so the brief opens with your day, then weather, markets, anything worth knowing. Edit freely — it is the voice of your wall |
| `prompts/x-trends.md` | cron prompt for X trends via the agent's `x_search` tool (xAI). Only needed if you don't use the X API path |

### The brief
The cron job's newest output under `~/.hermes/cron/output/<job id>/` is picked up by `server/collectors/brief.py`,
shown on the wall, and rendered to speech with [Piper](https://github.com/rhasspy/piper) (`piper_voice` in the
config — use the same voice your agent uses for TTS so it sounds like them). The takeover is **never automatic**: the
owner presses a key, or tells the agent "put my brief on the wall", which hits `GET /api/trigger?what=brief`.

### Alerts
`POST /api/alert` with `{title, body, image?, level?, ttl_minutes?, flash_seconds?}`. The skill shows the agent how to
spot a trip or birthday in `calendar.json`, pull the destination forecast, generate an image into
`server/web/img/alerts/`, and post once per milestone.

### Adapting the skill
The skill is written for a single owner. Replace the owner's name and the agent's name, and keep the two rules.
If your Hermes runs the collectors' host under a different path, update the paths at the top of the skill.
