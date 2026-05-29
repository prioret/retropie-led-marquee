# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

This project displays LED marquee images on a 48×192 HUB75 LED panel while a game is running in RetroArch. It runs across two Raspberry Pis.

## Hardware

- 2× Waveshare RGB-Matrix-P2.5-96x48-F flexible HUB75 LED matrix panels (48×96 each), arranged as a single 48×192 display
- Panels wired directly to Raspberry Pi GPIO (no HAT or driver board)
- `disable_hardware_pulsing = True` is required in `RGBMatrixOptions` (Waveshare-specified)

**E address line:** The 96×48 panel has 48 rows, which requires the HUB75 E address line. Without it, rows 16–23 and 40–47 are blank. In the `regular` hardware mapping: **Pi physical pin 10 → HUB75 output pin 16 (E)**. Blank rows in groups of 8 almost always mean E is not connected — not a multiplexing issue.

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

Logs to `/var/log/marquee_finder.log`.

## Script: `display_marquee.py` (Pi 2)

Run as a systemd service via `display_marquee.service`.

- Polls `INCOMING_FILE` (`/tmp/marquee_incoming/current.png`) every 0.5 s.
- On new file: checks `CACHE_DIR` (`/var/cache/marquee/`) for a pre-resized copy keyed by MD5 of the file content. If not cached, resizes the image to fit the panel with letterboxing on black and saves to cache.
- Displays the resized image via `matrix.SetImage()` using double-buffering (`SwapOnVSync`).
- Deletes the original file so the next SCP from Pi 1 triggers a new display cycle.

Hardware config at the top of the script: `ROWS_PER_PANEL`, `COLS_PER_PANEL`, `CHAIN_LENGTH`, `HARDWARE_MAPPING`.

**Panel config relationship:** `DISPLAY_WIDTH = COLS_PER_PANEL × CHAIN_LENGTH` and `DISPLAY_HEIGHT = ROWS_PER_PANEL`. If you change `CHAIN_LENGTH`, update `DISPLAY_WIDTH` to match, or the cache key and resize target will be wrong.

Logs to `/var/log/display_marquee.log`.

## Display stability requirements (Pi 2)

Three things are needed for flicker-free output:

1. **Realtime thread priority** — the service runs as `User=root` in `display_marquee.service`. Without root (or `cap_sys_nice`), the OS scheduler interrupts PWM timing, causing brightness instability and row flicker.

2. **CPU isolation** — dedicate one core to the matrix driver by appending `isolcpus=3` to `/boot/firmware/cmdline.txt` (single line, no newline) and rebooting. Confirm with `cat /sys/devices/system/cpu/isolated`.

3. **No desktop environment** — use Raspberry Pi OS Lite (64-bit). X11/window manager overhead causes PWM timing instability.

**Confirmed working PWM settings** (verified on fresh Raspberry Pi OS Lite install): `gpio_slowdown=4`, `pwm_lsb_nanoseconds=130`, `pwm_bits=11`, `brightness=100`. These are the defaults in `display_marquee.py`. Previous higher-slowdown/lower-quality workarounds (`gpio_slowdown=5`, `pwm_lsb_nanoseconds=250`, `pwm_bits=9`) were only needed on a desktop OS with background load.

## Deployment

**Pi 2 — set up Python virtual environment:**
```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
# Build and install rpi-rgb-led-matrix into the venv:
#   sudo apt-get install -y python3-dev cython3
#   cd ~/git/rpi-rgb-led-matrix && ~/path/to/venv/bin/pip install .
# See: https://github.com/hzeller/rpi-rgb-led-matrix
```

**Pi 1 — install service** (scripts expected at `/home/pi/retropie-led-marquee/`):
```bash
sudo cp marquee_finder.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable marquee_finder
sudo systemctl start marquee_finder
```

**Pi 2 — install service** (scripts expected at `/home/prioret/git/retropie-led-marquee/`):
```bash
sudo cp display_marquee.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable display_marquee
sudo systemctl start display_marquee
```

**After updating the service file:**
```bash
sudo cp display_marquee.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart display_marquee
```

**Check service status and logs:**
```bash
sudo systemctl status display_marquee
sudo journalctl -u display_marquee -f
```

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
exec -a retroarch sleep 3600 &
bash marquee_finder.sh
```

**Pi 2 — preview mode (no LED hardware):**
```bash
# rgbmatrix import fails gracefully; script prints what it would display
python3 display_marquee.py
# then drop a PNG into /tmp/marquee_incoming/current.png to trigger a cycle
```

**Pi 2 — hardware test** (requires rgbmatrix in venv):
```bash
sudo venv/bin/python3 test_matrix.py
```
Cycles through solid colours, gradient, checkerboard, border outline, pixel walk, and brightness fade. Use this to verify panel wiring, E address line, and PWM settings before running the service.
