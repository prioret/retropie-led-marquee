# RetroPie LED Marquee

Displays game marquee images on an LED matrix panel while a game is running in RetroArch.

## Hardware

- 2x [Waveshare RGB-Matrix-P2.5-96x48-F](https://www.waveshare.com/wiki/RGB-Matrix-P2.5-96x48-F) flexible HUB75 LED matrix panels (48×96 pixels each), arranged as a single 48×192 panel ([buy](https://www.amazon.com/dp/B0BRBDNT4L?ref=ppx_yo2ov_dt_b_fed_asin_title))
- Panels wired directly to Raspberry Pi GPIO (no HAT or driver board)

### E address line

The Waveshare 96×48 panel has 48 rows. Standard HUB75 address lines A–D (4 bits) can only address 16 rows per half-panel, covering 32 rows total. The **E address line** is required to address rows 16–23 in each half (physical rows 16–23 and 40–47). If E is not connected, those 8 rows will be blank.

In the hzeller `regular` hardware mapping, **E = GPIO 15 = Pi physical pin 10** (the RXD serial pin).

**Check continuity** (Pi powered off, multimeter in continuity mode) between:
- Pi header **pin 10** → HUB75 output connector **pin 16**

HUB75 16-pin IDC pinout (pin 1 = top-left when facing the connector):

```
 1  R1    2  G1
 3  B1    4  GND
 5  R2    6  G2
 7  B2    8  GND
 9  A    10  B
11  C    12  D
13  CLK  14  STR
15  OE   16  E
```

When wiring directly, connect **Pi physical pin 10** to **HUB75 pin 16** (E).

### hzeller rpi-rgb-led-matrix options

These are the options specified by Waveshare for the RGB-Matrix-P2.5-96x48-F panel with the [hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) library:

```
-D0 --led-no-hardware-pulse --led-cols=96 --led-rows=48 \
    --led-pwm-lsb-nanoseconds=130 --led-pwm-bits=11 \
    --led-brightness=100 --led-slowdown-gpio=4
```

| Flag | Value | Notes |
|------|-------|-------|
| `-D0` | multiplexing=0 | Direct (default); blank rows are an E address line issue, not multiplexing |
| `--led-no-hardware-pulse` | — | Waveshare-specified |
| `--led-cols` | 96 | |
| `--led-rows` | 48 | |
| `--led-pwm-lsb-nanoseconds` | 130 | Waveshare-specified for this panel |
| `--led-pwm-bits` | 11 | Colour depth |
| `--led-brightness` | 100 | Consider lower values (e.g. 50) to reduce heat on the flexible panel |
| `--led-slowdown-gpio` | 4 | Waveshare-specified; try 3 if display is stable |

In the Python API (`test_matrix.py`), these map to `RGBMatrixOptions` fields: `multiplexing`, `disable_hardware_pulsing`, `cols`, `rows`, `pwm_lsb_nanoseconds`, `pwm_bits`, `brightness`, `gpio_slowdown`.

## Architecture

Two Raspberry Pis are involved:

| Pi | Role |
|----|------|
| **Pi 1** (RetroPie) | Runs RetroArch. Polls every 2 s for the active game, finds its marquee PNG, and SCPs it to Pi 2 when it changes. |
| **Pi 2** (Display) | Watches for incoming images, resizes them to fit the 48×192 panel, and displays them via direct GPIO. |

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

**Permissions and display stability:**

The matrix driver needs two things to run cleanly:

1. **GPIO access** — add your user to the `gpio` group (one-time setup):
   ```bash
   sudo usermod -a -G gpio prioret
   ```

2. **Realtime thread priority** — without this the OS scheduler interrupts PWM timing, causing brightness instability and row flicker. Either run as root, or grant the capability to the venv Python binary:
   ```bash
   sudo setcap 'cap_sys_nice=eip' /home/prioret/git/retropie-led-marquee/venv/bin/python3
   ```
   The systemd service should run as root (`User=root` in the `.service` file) or have this capability set.

3. **CPU isolation** — for the most stable output, dedicate one CPU core to the matrix driver. Add `isolcpus=3` to the end of `/boot/cmdline.txt` (all on one line) and reboot:
   ```
   … existing options … isolcpus=3
   ```
   This prevents the kernel from scheduling other tasks onto core 3, eliminating the remaining brightness shimmer.

**Install service:**
```bash
sudo cp display_marquee.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable display_marquee
sudo systemctl start display_marquee
```

**After updating the service file** (e.g. changing `User`, `ExecStart`, etc.):
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

## Pi 2 — Fresh install from scratch

Use **Raspberry Pi OS Lite (64-bit)** — no desktop environment. The X11/window manager overhead causes PWM timing instability that manifests as brightness flicker on the LED panel.

### 1. Flash the SD card

Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/). In the OS customisation screen (gear icon), set:
- Hostname (e.g. `marqueepi`)
- Username and password
- Enable SSH
- Wi-Fi credentials if needed

### 2. First boot — update and install dependencies

```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y git python3-dev python3-venv cython3
```

### 3. CPU isolation — edit cmdline.txt

On Raspberry Pi OS Bookworm (current), the file is `/boot/firmware/cmdline.txt`. On Bullseye and earlier it is `/boot/cmdline.txt`.

The file is a **single line** — do not add a newline. Append `isolcpus=3` to the end:

```bash
sudo nano /boot/firmware/cmdline.txt
```

Before:
```
console=serial0,115200 console=tty1 root=PARTUUID=... rootfstype=ext4 fsck.repair=yes rootwait
```

After:
```
console=serial0,115200 console=tty1 root=PARTUUID=... rootfstype=ext4 fsck.repair=yes rootwait isolcpus=3
```

Reboot and confirm it took effect:
```bash
sudo reboot
cat /sys/devices/system/cpu/isolated   # should print: 3
```

### 4. Clone this repo

The service file expects the repo at `~/retropie-led-marquee`:

```bash
cd ~
git clone https://github.com/YOUR_USERNAME/retropie-led-marquee.git
```

### 5. Build and install rpi-rgb-led-matrix

```bash
cd ~
git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
cd ~/retropie-led-marquee
python3 -m venv venv
venv/bin/pip install --upgrade pip
cd ~/rpi-rgb-led-matrix
~/retropie-led-marquee/venv/bin/pip install .
```

### 6. Install Python dependencies

```bash
cd ~/retropie-led-marquee
venv/bin/pip install -r requirements.txt
```

### 7. Create required directories

```bash
sudo mkdir -p /var/logs /var/cache/marquee /tmp/marquee_incoming
```

### 8. Install and enable the service

Open `display_marquee.service` and verify the `ExecStart` paths match your username and clone location, then:

```bash
sudo cp ~/retropie-led-marquee/display_marquee.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable display_marquee
sudo systemctl start display_marquee
```

### 9. Verify

```bash
sudo systemctl status display_marquee
sudo venv/bin/python3 ~/retropie-led-marquee/test_matrix.py   # quick hardware test
```
