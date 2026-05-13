# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

This project displays LED marquee images on a 48×192 HUB75 LED panel while a game is running in RetroArch. It runs across two Raspberry Pis.

## Architecture

| Pi | Role | Key files |
|----|------|-----------|
| **Pi 1** (RetroPie) | Polls for the active game, resolves its marquee PNG, SCPs it to Pi 2 when it changes | `marquee_finder.sh` |
| **Pi 2** (Display) | Watches for incoming images, resizes to fit the panel, displays via rpi-rgb-led-matrix, caches resized output | `display_marquee.py`, `display_marquee.service` |

## Pi 1 runtime environment

- Runs as user `pi` on the RetroPie machine
- Marquee images scraped by [Skyscraper](https://github.com/muldjord/skyscraper): `/home/pi/RetroPie/roms/<system>/media/marquees/<rom_name>.png`
- Two temp files written externally (EmulationStation event script or runcommand hook):
  - `/tmp/current_system.txt` — short system name (e.g. `snes`, `megadrive`)
  - `/tmp/current_rom.txt` — full path to the ROM file
- Requires passwordless SSH access from Pi 1 to Pi 2

## Script: `marquee_finder.sh` (Pi 1)

Polling daemon — runs continuously, does not exit normally. Managed by `marquee_finder.service`.

Every 2 seconds:
1. If RetroArch is running and temp files are populated, resolves the Skyscraper marquee PNG for the active game.
2. Otherwise falls back to `DEFAULT_IMAGE` (configurable at the top of the script).
3. If the resolved path differs from the last sent path, SCPs the file to Pi 2 via a two-step `scp` + `ssh mv` to avoid partial reads.

Configuration variables at the top of the script: `DEFAULT_IMAGE`, `PI2_USER`, `PI2_HOST`, `PI2_DEST`, `CHECK_INTERVAL`.

## Script: `display_marquee.py` (Pi 2)

Run as a systemd service via `display_marquee.service`.

- Polls `INCOMING_FILE` (`/tmp/marquee_incoming/current.png`) every 0.5 s.
- On new file: checks `CACHE_DIR` (`/var/cache/marquee/`) for a pre-resized copy keyed by MD5 of the file content. If not cached, resizes the image to fit 48×192 with letterboxing on black and saves to cache.
- Displays the resized image via `matrix.SetImage()` (rpi-rgb-led-matrix).
- Deletes the original file so the next SCP from Pi 1 triggers a new display cycle.

Hardware config at the top of the script: `ROWS_PER_PANEL`, `COLS_PER_PANEL`, `CHAIN_LENGTH`, `HARDWARE_MAPPING`.

## Testing

No automated test suite. Manual testing:

**Pi 1 — syntax check:**
```bash
bash -n marquee_finder.sh
```

**Pi 1 — simulate a running game:**
```bash
echo "snes" > /tmp/current_system.txt
echo "/home/pi/RetroPie/roms/snes/MyGame.smc" > /tmp/current_rom.txt
# ensure retroarch process is running, then:
bash marquee_finder.sh
```

**Pi 2 — preview mode (no LED hardware):**
```bash
# rgbmatrix import will fail gracefully; script prints what it would display
python3 display_marquee.py
# then drop a PNG into /tmp/marquee_incoming/current.png to trigger a cycle
```
