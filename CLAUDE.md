# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

This project displays LED marquee images on a 48×192 HUB75 LED panel while a game is running in RetroArch. It runs across two Raspberry Pis.

## Hardware

- 2× HUB75 LED matrix panels (48×96 each), arranged as a single 48×192 display
- [ElectroDragon RGB LED Matrix Panel Drive Board](https://www.electrodragon.com/product/rgb-matrix-panel-drive-board-raspberry-pi/) for Raspberry Pi — panels connected to port 0
- `disable_hardware_pulsing = True` is required in `RGBMatrixOptions` for this board

## Architecture

| Pi | Role | Key files |
|----|------|-----------|
| **Pi 1** (RetroPie) | Polls for the active game, resolves its marquee PNG, SCPs it to Pi 2 when it changes | `marquee_finder.sh`, `marquee_finder.service` |
| **Pi 2** (Display) | Watches for incoming images, resizes to fit the panel, displays via rpi-rgb-led-matrix, caches resized output | `display_marquee.py`, `display_marquee.service` |

## Pi 1 runtime environment

- Runs as user `pi` on the RetroPie machine
- Marquee images scraped by [Skyscraper](https://github.com/muldjord/skyscraper): `/home/pi/RetroPie/roms/<system>/media/marquees/<rom_name>.png`
- Two temp files written externally (EmulationStation event script or runcommand hook):
  - `/tmp/current_system.txt` — short system name (e.g. `snes`, `megadrive`)
  - `/tmp/current_rom.txt` — full path to the ROM file
- Requires passwordless SSH access from Pi 1 to Pi 2 (`ssh-copy-id pi@pi2`)

## Script: `marquee_finder.sh` (Pi 1)

Polling daemon — runs continuously, does not exit normally. Managed by `marquee_finder.service`.

Every 2 seconds:
1. If RetroArch is running and temp files are populated, resolves the Skyscraper marquee PNG for the active game.
2. Otherwise falls back to `DEFAULT_IMAGE` (configurable at the top of the script).
3. If the resolved path differs from the last sent path, SCPs the file to Pi 2 via a two-step `scp` + `ssh mv` to avoid partial reads.

Configuration variables at the top of the script: `DEFAULT_IMAGE`, `PI2_USER`, `PI2_HOST`, `PI2_DEST`, `CHECK_INTERVAL`.

Logs to `/var/logs/marquee_finder.log` (note: non-standard `logs` path, not `/var/log/`).

## Script: `display_marquee.py` (Pi 2)

Run as a systemd service via `display_marquee.service`.

- Polls `INCOMING_FILE` (`/tmp/marquee_incoming/current.png`) every 0.5 s.
- On new file: checks `CACHE_DIR` (`/var/cache/marquee/`) for a pre-resized copy keyed by MD5 of the file content. If not cached, resizes the image to fit 48×192 with letterboxing on black and saves to cache.
- Displays the resized image via `matrix.SetImage()` (rpi-rgb-led-matrix).
- Deletes the original file so the next SCP from Pi 1 triggers a new display cycle.

Hardware config at the top of the script: `ROWS_PER_PANEL`, `COLS_PER_PANEL`, `CHAIN_LENGTH`, `HARDWARE_MAPPING`.

**Panel config relationship:** `DISPLAY_WIDTH = COLS_PER_PANEL × CHAIN_LENGTH` and `DISPLAY_HEIGHT = ROWS_PER_PANEL`. If you change `CHAIN_LENGTH`, update `DISPLAY_WIDTH` to match, or the cache key and resize target will be wrong.

Logs to `/var/logs/display_marquee.log` (same non-standard path as above).

## Deployment

**Pi 2 — set up Python virtual environment:**
```bash
# --system-site-packages lets the venv see rgbmatrix, which is built from source system-wide
python3 -m venv --system-site-packages venv
venv/bin/pip install -r requirements.txt
# Build and install rpi-rgb-led-matrix system-wide per https://github.com/hzeller/rpi-rgb-led-matrix
```

**Pi 1 — install service:**
```bash
sudo cp marquee_finder.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable marquee_finder
sudo systemctl start marquee_finder
```

**Pi 2 — install service:**
```bash
sudo cp display_marquee.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable display_marquee
sudo systemctl start display_marquee
```

Both services expect the scripts at `/home/pi/retropie-led-marquee/`.

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
# Start a dummy process named 'retroarch' so pgrep -x retroarch succeeds:
sleep 3600 &
exec -a retroarch sleep 3600 &
bash marquee_finder.sh
```

**Pi 2 — preview mode (no LED hardware):**
```bash
# rgbmatrix import will fail gracefully; script prints what it would display
python3 display_marquee.py
# then drop a PNG into /tmp/marquee_incoming/current.png to trigger a cycle
```
