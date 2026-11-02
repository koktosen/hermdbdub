#!/usr/bin/env bash
# Route the kiosk's audio to every output that will actually take it: HDMI (when the TV has an audio sink),
# the 3.5 mm jack, any USB speaker. Writes /etc/asound.conf and is re-run at boot and nightly, so moving the Pi
# to a different TV or plugging in a speaker needs no configuration.
#
# Why probe: a TV with no HDMI audio block makes the HDMI PCM fail to open (error 524), and an ALSA "multi" device
# fails as a whole if any slave fails, so only the outputs that pass a one-second silent playback are fanned out.
# Run as root:  sudo audio-route.sh            (prints the outputs chosen)
set -uo pipefail

ok=()
while read -r idx name; do
	[[ -z "$idx" ]] && continue
	if timeout 5 aplay -q -D "plughw:${idx},0" -d 1 -f S16_LE -r 48000 -c 2 /dev/zero >/dev/null 2>&1; then
		ok+=("$idx:$name")
	fi
done < <(aplay -l 2>/dev/null | sed -nE 's/^card ([0-9]+): ([^ ]+).*/\1 \2/p' | sort -u)

conf=/etc/asound.conf
header="# written by audio-route.sh ($(date -Is)); outputs that accepted playback: ${ok[*]:-none}"
if (( ${#ok[@]} == 0 )); then
	printf '%s\n# nothing accepted audio; default to card 0 so a speaker plugged in later works\ndefaults.pcm.card 0\ndefaults.ctl.card 0\n' "$header" > "$conf"
elif (( ${#ok[@]} == 1 )); then
	c="${ok[0]%%:*}"
	printf '%s\ndefaults.pcm.card %s\ndefaults.ctl.card %s\n' "$header" "$c" "$c" > "$conf"
else
	{
		echo "$header"
		echo 'pcm.!default { type plug; slave.pcm "allouts" }'
		echo "ctl.!default { type hw; card ${ok[0]%%:*} }"
		echo 'pcm.allouts {'
		echo '  type route'
		echo '  slave.pcm {'
		echo '    type multi'
		i=0
		for o in "${ok[@]}"; do
			echo "    slaves.s${i} { pcm \"hw:${o%%:*},0\"; channels 2 }"
			echo "    bindings.$((i * 2)) { slave s${i}; channel 0 }"
			echo "    bindings.$((i * 2 + 1)) { slave s${i}; channel 1 }"
			((i++))
		done
		echo '  }'
		for ((j = 0; j < i; j++)); do
			echo "  ttable.0.$((j * 2)) 1"
			echo "  ttable.1.$((j * 2 + 1)) 1"
		done
		echo '}'
	} > "$conf"
fi
echo "audio outputs: ${ok[*]:-none}  -> $conf"
