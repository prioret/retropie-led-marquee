#!/usr/bin/env python3

import hashlib
import logging
import os
import png
import inotify_simple
from PIL import Image, ImageFile
Image.init()

try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions
    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False

# --- Configuration ---
INCOMING_FILE    = "/tmp/marquee_incoming/current.png"
CLEAR_FILE       = "/tmp/marquee_incoming/clear"
DEFAULT_IMAGE    = "/home/prioret/retropie-led-marquee/default.png"
CACHE_DIR        = "/var/cache/marquee"
DISPLAY_WIDTH    = 192
DISPLAY_HEIGHT   = 48
ROWS_PER_PANEL   = 48
COLS_PER_PANEL   = 96
CHAIN_LENGTH     = 2
HARDWARE_MAPPING = "regular"   # use "adafruit-hat" if using Adafruit bonnet

# LED matrix hardware settings (Waveshare RGB-Matrix-P2.5-96x48-F, direct GPIO)
# Matches: -D0 --led-no-hardware-pulse --led-cols=96 --led-rows=48
#          --led-pwm-lsb-nanoseconds 130 --led-pwm-bits=11 --led-brightness=100 --led-slowdown-gpio=4
BRIGHTNESS    = 100
GPIO_SLOWDOWN = 5
PWM_LSB_NS    = 200
PWM_BITS      = 9
MULTIPLEXING  = 0     # -D0
# ---------------------


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler()],
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
    options.limit_refresh_rate_hz    = 120
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


def display_file(matrix, path):
    with open(path, 'rb') as f:
        data = f.read()
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError(
            f"Not a valid PNG ({len(data)} bytes, header={data[:8].hex() if data else 'empty'})"
        )
    content_hash = hashlib.md5(data).hexdigest()
    cached = cache_path(content_hash)

    if os.path.exists(cached):
        img = Image.open(cached).convert("RGB")
        cache_status = "hit"
    else:
        img = resize_to_fill(_load_png(path).convert("RGB"))
        img.save(cached, format="PNG")
        cache_status = "miss"

    if matrix:
        canvas = matrix.CreateFrameCanvas()
        canvas.SetImage(img)
        matrix.SwapOnVSync(canvas)
    else:
        logging.info("[preview] %s (%s)", path, img.size)

    logging.info("Displayed %s (cache %s)", os.path.basename(path), cache_status)


def main():
    setup_logging()
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.chmod(CACHE_DIR, 0o777)
    incoming_dir = os.path.dirname(INCOMING_FILE)
    os.makedirs(incoming_dir, exist_ok=True)
    os.chmod(incoming_dir, 0o777)

    logging.info("display_marquee starting")
    matrix = setup_matrix()

    if os.path.exists(DEFAULT_IMAGE):
        try:
            display_file(matrix, DEFAULT_IMAGE)
        except Exception as exc:
            logging.error("Error displaying default image: %s", exc, exc_info=True)
    else:
        logging.warning("Default image not found: %s", DEFAULT_IMAGE)

    inotify = inotify_simple.INotify()
    inotify.add_watch(incoming_dir, inotify_simple.flags.MOVED_TO | inotify_simple.flags.CLOSE_WRITE)
    logging.info("Watching %s", incoming_dir)

    target = os.path.basename(INCOMING_FILE)
    clear  = os.path.basename(CLEAR_FILE)
    while True:
        for event in inotify.read():
            logging.debug("inotify event: mask=%s name=%s", event.mask, event.name)
            if event.name == clear:
                try:
                    os.remove(CLEAR_FILE)
                except OSError:
                    pass
                if os.path.exists(DEFAULT_IMAGE):
                    try:
                        display_file(matrix, DEFAULT_IMAGE)
                    except Exception as exc:
                        logging.error("Error displaying default image: %s", exc, exc_info=True)
                else:
                    logging.warning("Default image not found: %s", DEFAULT_IMAGE)
            elif event.name == target:
                try:
                    display_file(matrix, INCOMING_FILE)
                    os.remove(INCOMING_FILE)
                except Exception as exc:
                    logging.error("Error processing %s: %s", INCOMING_FILE, exc, exc_info=True)
                    try:
                        os.remove(INCOMING_FILE)
                        logging.warning("Deleted %s after error", INCOMING_FILE)
                    except OSError:
                        pass


if __name__ == "__main__":
    main()
