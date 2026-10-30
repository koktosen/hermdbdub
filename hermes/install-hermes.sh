#!/usr/bin/env bash
# Wires a Hermes agent into hermdbw: installs the wall skill and creates the two cron jobs (morning brief,
# X trends) if jobs with those names don't already exist. Idempotent. Prints the job ids to put in config.yaml.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
command -v hermes >/dev/null || { echo "hermes CLI not found — install Hermes Agent first (https://github.com/NousResearch/hermes-agent)"; exit 1; }

echo "==> skill → $HERMES_HOME/skills/wall-brief/SKILL.md"
mkdir -p "$HERMES_HOME/skills/wall-brief"
cp "$HERE/wall-brief.SKILL.md" "$HERMES_HOME/skills/wall-brief/SKILL.md"

job_id() { hermes cron list 2>/dev/null | grep -F "$1" | grep -oE '[0-9a-f]{12}' | head -1 || true; }
ensure_job() {  # name schedule promptfile deliver
	local id; id="$(job_id "$1")"
	if [[ -z "$id" ]]; then
		echo "==> creating cron job $1 ($2)"
		hermes cron create "$2" "$(cat "$3")" --name "$1" --deliver "$4" >/dev/null
		id="$(job_id "$1")"
	else
		echo "==> cron job $1 already exists ($id)"
	fi
	echo "    $1 = $id"
}
ensure_job "hermdbw-morning-brief" "30 7 * * *" "$HERE/prompts/morning-brief.md" "telegram"
ensure_job "hermdbw-x-trends"      "0 7-22/3 * * *" "$HERE/prompts/x-trends.md"  "local"

cat <<MSG

Put the ids above into server/config.yaml:
  hermes_brief_job:   <hermdbw-morning-brief id>
  hermes_xtrends_job: <hermdbw-x-trends id>
X trends need xAI access (XAI_API_KEY in $HERMES_HOME/.env, then enable X Search in 'hermes tools'); without it the
column says so instead of guessing. Restart the gateway after editing .env. Your agent needs a NEW chat session
to notice the skill ('/new' on Telegram).
MSG
