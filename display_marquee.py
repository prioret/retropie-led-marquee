#!/usr/bin/env python3

import hashlib
import logging
import os
import time
from PIL import Image

try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions
    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False

# --- Configuration ---
INCOMING_FILE    = "/tmp/marquee_incoming/current.png"
CACHE_DIR        = "/var/cache/marquee"
LOG_FILE         = "/var/logs/display_marquee.log"
DISPLAY_WIDTH    = 192
DISPLAY_HEIGHT   = 48
ROWS_PER_PANEL   = 48
COLS_PER_PANEL   = 96
CHAIN_LENGTH     = 2
HARDWARE_MAPPING = "regular"   # use "adafruit-hat" if using Adafruit bonnet
CHECK_INTERVAL   = 0.5         # seconds between polls

# LED matrix hardware settings (Waveshare RGB-Matrix-P2.5-96x48-F + ElectroDragon board)
BRIGHTNESS       = 50    # Waveshare specifies 100; lower reduces heat on flexible panel
GPIO_SLOWDOWN    = 4     # Waveshare-specified for this panel
PWM_LSB_NS       = 130   # Waveshare-specified
PWM_BITS         = 11    # Waveshare-specified colour depth
ROW_ADDRESS_TYPE = 0     # 0 = default; try 5 if rows look shuffled
MULTIPLEXING     = 0     # 0 = direct (Waveshare-specified via -D0)
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
    options.row_address_type         = ROW_ADDRESS_TYPE
    options.multiplexing             = MULTIPLEXING
    options.disable_hardware_pulsing = True        # required for ElectroDragon board
    return RGBMatrix(options=options)


def file_hash(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def cache_path(content_hash):
    return os.path.join(CACHE_DIR, f"{content_hash}_{DISPLAY_WIDTH}x{DISPLAY_HEIGHT}.png")


def resize_to_fit(img):
    """Fit img inside DISPLAY_WIDTH x DISPLAY_HEIGHT, centred on black."""
    img_ratio = img.width / img.height
    target_ratio = DISPLAY_WIDTH / DISPLAY_HEIGHT

    if img_ratio > target_ratio:
        new_w = DISPLAY_WIDTH
        new_h = int(DISPLAY_WIDTH / img_ratio)
    else:
        new_h = DISPLAY_HEIGHT
        new_w = int(DISPLAY_HEIGHT * img_ratio)

    resized = img.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), (0, 0, 0))
    canvas.paste(resized, ((DISPLAY_WIDTH - new_w) // 2, (DISPLAY_HEIGHT - new_h) // 2))
    return canvas


def process_and_display(matrix, incoming):
    content_hash = file_hash(incoming)
    cached = cache_path(content_hash)

    if os.path.exists(cached):
        logging.info("Cache hit for %s, loading %s", incoming, cached)
        img = Image.open(cached).convert("RGB")
    else:
        logging.info("Cache miss for %s, resizing to %dx%d", incoming, DISPLAY_WIDTH, DISPLAY_HEIGHT)
        img = resize_to_fit(Image.open(incoming).convert("RGB"))
        img.save(cached)
        logging.info("Cached resized image at %s", cached)

    if matrix:
        matrix.SetImage(img)
        logging.info("Displayed %s on LED matrix", incoming)
    else:
        logging.info("[preview] Would display %s (%s), cached at %s", incoming, img.size, cached)

    os.remove(incoming)
    logging.info("Deleted original %s", incoming)


def main():
    setup_logging()
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(INCOMING_FILE), exist_ok=True)

    logging.info("display_marquee starting, watching %s", INCOMING_FILE)
    matrix = setup_matrix()
    if matrix:
        logging.info("LED matrix initialised (%dx%d, chain %d)", ROWS_PER_PANEL, COLS_PER_PANEL, CHAIN_LENGTH)

    while True:
        if os.path.exists(INCOMING_FILE):
            try:
                process_and_display(matrix, INCOMING_FILE)
            except Exception as exc:
                logging.error("Error processing %s: %s", INCOMING_FILE, exc)
                try:
                    os.remove(INCOMING_FILE)
                    logging.warning("Deleted %s after error", INCOMING_FILE)
                except OSError:
                    pass
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
