# RetroPie LED Marquee

Displays game marquee images on an LED matrix panel while a game is running in RetroArch.

## Hardware

- 2x [HUB75 LED matrix panels](https://www.amazon.com/dp/B0BRBDNT4L?ref=ppx_yo2ov_dt_b_fed_asin_title) (48×96 pixels each), arranged as a single 48×192 panel
- [ElectroDragon RGB LED Matrix Panel Drive Board for Raspberry Pi](https://www.electrodragon.com/product/rgb-matrix-panel-drive-board-raspberry-pi/) — panels connected to port 0

The drive board documentation is available [here](https://w2.electrodragon.com/board-series-dat/RMP-driver-dat/RMP-driver-dat.md).

## Architecture

Two Raspberry Pis are involved:

| Pi | Role |
|----|------|
| **Pi 1** (RetroPie) | Runs RetroArch. Polls every 2 s for the active game, finds its marquee PNG, and SCPs it to Pi 2 when it changes. |
| **Pi 2** (Display) | Has the ElectroDragon HUB75 hat. Watches for incoming images, resizes them to fit the 48×192 panel, and displays them. |

## Pi 1 — `marquee_finder.sh`

Runs as a background daemon on the RetroPie machine.

**What it does:**
- Every 2 seconds, checks whether RetroArch is running.
- If a game is running, resolves the Skyscraper marquee PNG for that game.
- If no game is running, falls back to a configurable default image.
- SCPs the image to Pi 2 only when the image changes.

**Configuration** (top of script):

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_IMAGE` | `/home/pi/RetroPie/marquees/default.png` | Shown when no game is running |
| `PI2_USER` | `pi` | SSH user on Pi 2 |
| `PI2_HOST` | `pi2` | Hostname or IP of Pi 2 |
| `PI2_DEST` | `/tmp/marquee_incoming/current.png` | Destination path on Pi 2 |
| `CHECK_INTERVAL` | `2` | Polling interval in seconds |

**Prerequisites:**
- Pi 1 must have passwordless SSH access to Pi 2 (`ssh-copy-id pi@pi2`).
- An EmulationStation event script or runcommand hook must write:
  - `/tmp/current_system.txt` — short system name (e.g. `snes`)
  - `/tmp/current_rom.txt` — full path to the ROM file

**Install service:**
```bash
sudo cp marquee_finder.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable marquee_finder
sudo systemctl start marquee_finder
```

## Pi 2 — `display_marquee.py`

Runs as a systemd service on the display Pi.

**What it does:**
- Polls `/tmp/marquee_incoming/current.png` every 0.5 s.
- When a new file appears: resizes it to fit 48×192 (preserving aspect ratio, letterboxed on black), displays it on the LED matrix, then deletes the original.
- Caches resized images in `/var/cache/marquee/` keyed by file content hash, so the same marquee is not resized twice.

**Configuration** (top of script):

| Variable | Default | Description |
|----------|---------|-------------|
| `INCOMING_FILE` | `/tmp/marquee_incoming/current.png` | Where Pi 1 delivers images |
| `CACHE_DIR` | `/var/cache/marquee` | Resized image cache |
| `HARDWARE_MAPPING` | `regular` | rpi-rgb-led-matrix mapping (`adafruit-hat`, etc.) |
| `DISPLAY_WIDTH/HEIGHT` | `192` / `48` | LED panel resolution |

**Install dependencies:**
```bash
pip3 install Pillow
# Follow https://github.com/hzeller/rpi-rgb-led-matrix for the rgbmatrix library
```

**Install service:**
```bash
sudo cp display_marquee.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable display_marquee
sudo systemctl start display_marquee
```
