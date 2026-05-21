#!/usr/bin/env python3

import hashlib
import logging
import os
import time
import png
from PIL import Image, ImageFile
Image.init()

try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions
    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False

# --- Configuration ---
INCOMING_FILE    = "/tmp/marquee_incoming/current.png"
CACHE_DIR        = "/var/cache/marquee"
LOG_FILE         = "/var/log/display_marquee.log"
DISPLAY_WIDTH    = 192
DISPLAY_HEIGHT   = 48
ROWS_PER_PANEL   = 48
COLS_PER_PANEL   = 96
CHAIN_LENGTH     = 2
HARDWARE_MAPPING = "regular"   # use "adafruit-hat" if using Adafruit bonnet
CHECK_INTERVAL   = 0.5         # seconds between polls

# LED matrix hardware settings (Waveshare RGB-Matrix-P2.5-96x48-F, direct GPIO)
# Matches: -D0 --led-no-hardware-pulse --led-cols=96 --led-rows=48
#          --led-pwm-lsb-nanoseconds 130 --led-pwm-bits=11 --led-brightness=100 --led-slowdown-gpio=4
BRIGHTNESS    = 100
GPIO_SLOWDOWN = 4
PWM_LSB_NS    = 130
PWM_BITS      = 11
MULTIPLEXING  = 0     # -D0
# ---------------------


def setup_logging():
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(),
        ],
    )


def setup_matrix():
    if not HARDWARE_AVAILABLE:
        logging.warning("rgbmatrix not available, running in preview mode")
        return None
    options = RGBMatrixOptions()
    options.rows                     = ROWS_PER_PANEL
    options.cols                     = COLS_PER_PANEL
    options.chain_length             = CHAIN_LENGTH
    options.hardware_mapping         = HARDWARE_MAPPING
    options.brightness               = BRIGHTNESS
    options.gpio_slowdown            = GPIO_SLOWDOWN
    options.pwm_lsb_nanoseconds      = PWM_LSB_NS
    options.pwm_bits                 = PWM_BITS
    options.multiplexing             = MULTIPLEXING
    options.disable_hardware_pulsing = True
    return RGBMatrix(options=options)


def cache_path(content_hash):
    return os.path.join(CACHE_DIR, f"{content_hash}_{DISPLAY_WIDTH}x{DISPLAY_HEIGHT}.png")


def _load_png(path):
    """Load a PNG via pypng (tolerates bad CRCs and non-standard chunks)."""
    reader = png.Reader(filename=path)
    width, height, rows, info = reader.asDirect()
    planes = info['planes']
    bitdepth = info['bitdepth']
    row_list = list(rows)
    if bitdepth == 16:
        raw = b''.join(bytes(v >> 8 for v in row) for row in row_list)
    else:
        raw = b''.join(bytes(row) for row in row_list)
    mode = {1: 'L', 2: 'LA', 3: 'RGB', 4: 'RGBA'}[planes]
    return Image.frombytes(mode, (width, height), raw)


def resize_to_fill(img):
    """Scale img to cover DISPLAY_WIDTH x DISPLAY_HEIGHT, centre-crop the overflow."""
    img_ratio = img.width / img.height
    target_ratio = DISPLAY_WIDTH / DISPLAY_HEIGHT

    if img_ratio > target_ratio:
        new_h = DISPLAY_HEIGHT
        new_w = int(DISPLAY_HEIGHT * img_ratio)
    else:
        new_w = DISPLAY_WIDTH
        new_h = int(DISPLAY_WIDTH / img_ratio)

    resized = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - DISPLAY_WIDTH) // 2
    top = (new_h - DISPLAY_HEIGHT) // 2
    return resized.crop((left, top, left + DISPLAY_WIDTH, top + DISPLAY_HEIGHT))


def process_and_display(matrix, incoming):
    with open(incoming, 'rb') as f:
        data = f.read()
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError(
            f"Not a valid PNG ({len(data)} bytes, header={data[:8].hex() if data else 'empty'})"
        )
    content_hash = hashlib.md5(data).hexdigest()
    cached = cache_path(content_hash)

    if os.path.exists(cached):
        logging.info("Cache hit for %s, loading %s", incoming, cached)
        img = Image.open(cached).convert("RGB")
    else:
        logging.info("Cache miss for %s, resizing to %dx%d", incoming, DISPLAY_WIDTH, DISPLAY_HEIGHT)
        img = resize_to_fill(_load_png(incoming).convert("RGB"))
        img.save(cached, format="PNG")
        logging.info("Cached resized image at %s", cached)

    if matrix:
        canvas = matrix.CreateFrameCanvas()
        canvas.SetImage(img)
        matrix.SwapOnVSync(canvas)
        logging.info("Displayed %s on LED matrix", incoming)
    else:
        logging.info("[preview] Would display %s (%s), cached at %s", incoming, img.size, cached)

    os.remove(incoming)
    logging.info("Deleted original %s", incoming)


def main():
    setup_logging()
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.chmod(CACHE_DIR, 0o777)
    incoming_dir = os.path.dirname(INCOMING_FILE)
    os.makedirs(incoming_dir, exist_ok=True)
    os.chmod(incoming_dir, 0o777)

    logging.info("display_marquee starting, watching %s", INCOMING_FILE)
    matrix = setup_matrix()
    if matrix:
        logging.info("LED matrix initialised (%dx%d, chain %d)", ROWS_PER_PANEL, COLS_PER_PANEL, CHAIN_LENGTH)

    while True:
        if os.path.exists(INCOMING_FILE):
            try:
                process_and_display(matrix, INCOMING_FILE)
            except Exception as exc:
                logging.error("Error processing %s: %s", INCOMING_FILE, exc, exc_info=True)
                try:
                    os.remove(INCOMING_FILE)
                    logging.warning("Deleted %s after error", INCOMING_FILE)
                except OSError:
                    pass
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
