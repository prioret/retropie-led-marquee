#!/usr/bin/env python3
"""
Visual test script for Waveshare 96x48 flexible LED matrix, wired directly to Raspberry Pi GPIO.

Run with:
    venv/bin/python3 test_matrix.py

Requires rpi-rgb-led-matrix Python bindings installed into the venv:
    sudo apt-get install -y python3-dev cython3
    cd ~/git/rpi-rgb-led-matrix && ~/git/retropie-led-marquee/venv/bin/pip install .
"""

import sys
import time

try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions
except ImportError:
    print("ERROR: rgbmatrix not found.")
    print("Install it into the venv:")
    print("  cd ~/git/rpi-rgb-led-matrix && ~/git/retropie-led-marquee/venv/bin/pip install .")
    sys.exit(1)

# --- Hardware configuration ---
ROWS       = 48    # physical rows on the Waveshare 96x48 panel
COLS       = 96    # physical columns
CHAIN      = 1     # single panel for power supply testing
BRIGHTNESS = 50    # Waveshare uses 100; keeping lower to limit heat on flexible panel

# Waveshare-specified values for the RGB-Matrix-P2.5-96x48-F (-D0 flag set):
GPIO_SLOW        = 5    # increased from Waveshare-specified 4 for stability
PWM_LSB_NS       = 250  # increased from 130 for stable brightness
PWM_BITS         = 9    # reduced from 11 for stable brightness
LIMIT_REFRESH_HZ = 60   # cap refresh rate for stable PWM brightness
PWM_DITHER_BITS  = 1    # temporal dithering to smooth low-brightness flicker

# Row address type: 0 = default.
# This panel uses SM5368PF XOR-shift row drivers (non-standard HUB75).
# If rows look shuffled/doubled, try ROW_ADDR_TYPE = 5.
ROW_ADDR_TYPE    = 0

# Multiplexing: Waveshare specifies -D0 (direct/default).
# Blank sequential rows are most likely a missing E address line, not multiplexing.
# See README.md — Pi physical pin 10 must connect to HUB75 output pin 16.
MULTIPLEXING     = 0

WIDTH = COLS * CHAIN


def make_matrix():
    opts = RGBMatrixOptions()
    opts.rows                     = ROWS
    opts.cols                     = COLS
    opts.chain_length             = CHAIN
    opts.hardware_mapping         = "regular"   # standard direct GPIO mapping
    opts.brightness               = BRIGHTNESS
    opts.gpio_slowdown            = GPIO_SLOW
    opts.pwm_lsb_nanoseconds      = PWM_LSB_NS
    opts.pwm_bits                 = PWM_BITS
    opts.row_address_type         = ROW_ADDR_TYPE
    opts.multiplexing             = MULTIPLEXING
    opts.disable_hardware_pulsing = True        # Waveshare-specified
    opts.limit_refresh_rate_hz    = LIMIT_REFRESH_HZ
    opts.pwm_dither_bits          = PWM_DITHER_BITS
    return RGBMatrix(options=opts)


def fill(canvas, r, g, b):
    for y in range(ROWS):
        for x in range(WIDTH):
            canvas.SetPixel(x, y, r, g, b)


def run_test(matrix, label, draw_fn, hold=1.5):
    print(f"  {label}")
    canvas = matrix.CreateFrameCanvas()
    draw_fn(canvas)
    matrix.SwapOnVSync(canvas)
    time.sleep(hold)


def test_solid_colors(matrix):
    for label, r, g, b in [
        ("Solid red",   255, 0,   0),
        ("Solid green", 0,   255, 0),
        ("Solid blue",  0,   0,   255),
        ("Solid white", 255, 255, 255),
    ]:
        def draw(canvas, r=r, g=g, b=b):
            fill(canvas, r, g, b)
        run_test(matrix, label, draw)


def test_gradient(matrix):
    def draw(canvas):
        for x in range(WIDTH):
            t = x / WIDTH
            if t < 1 / 3:
                r, g, b = 255, int(t * 3 * 255), 0
            elif t < 2 / 3:
                r, g, b = int((1 - (t - 1 / 3) * 3) * 255), 255, 0
            else:
                r, g, b = 0, int((1 - (t - 2 / 3) * 3) * 255), 255
            for y in range(ROWS):
                canvas.SetPixel(x, y, r, g, b)
    run_test(matrix, "Horizontal rainbow gradient", draw, hold=2)


def test_checkerboard(matrix, square=8):
    def draw(canvas):
        for y in range(ROWS):
            for x in range(WIDTH):
                on = ((x // square) + (y // square)) % 2 == 0
                v = 255 if on else 0
                canvas.SetPixel(x, y, v, v, v)
    run_test(matrix, f"Checkerboard ({square}px squares)", draw, hold=2)


def test_border(matrix):
    def draw(canvas):
        for x in range(WIDTH):
            canvas.SetPixel(x, 0,        255, 0, 0)
            canvas.SetPixel(x, ROWS - 1, 255, 0, 0)
        for y in range(ROWS):
            canvas.SetPixel(0,         y, 0, 255, 0)
            canvas.SetPixel(WIDTH - 1, y, 0, 255, 0)
    run_test(matrix, "Red/green border outline", draw, hold=2)


def test_pixel_walk(matrix):
    """Light a single pixel scanning left-to-right, top-to-bottom."""
    print("  Single-pixel walk (tests individual pixel addressing)")
    step = 4  # advance by 4 pixels at a time for reasonable speed
    canvas = matrix.CreateFrameCanvas()
    for y in range(0, ROWS, step):
        for x in range(0, WIDTH, step):
            canvas.Clear()
            canvas.SetPixel(x, y, 255, 255, 255)
            matrix.SwapOnVSync(canvas)
            time.sleep(0.01)


def test_brightness_fade(matrix):
    print("  Brightness fade (white, in then out)")
    for level in list(range(0, 101, 4)) + list(range(100, -1, -4)):
        canvas = matrix.CreateFrameCanvas()
        v = int(level * 2.55)
        fill(canvas, v, v, v)
        matrix.SwapOnVSync(canvas)
        time.sleep(0.03)


def main():
    print(f"Initialising {WIDTH}×{ROWS} matrix  "
          f"(chain={CHAIN}, brightness={BRIGHTNESS}%, gpio_slowdown={GPIO_SLOW}, "
          f"pwm_bits={PWM_BITS}, pwm_lsb_ns={PWM_LSB_NS}, "
          f"row_addr_type={ROW_ADDR_TYPE}, multiplexing={MULTIPLEXING}, "
          f"limit_refresh_hz={LIMIT_REFRESH_HZ})")
    print("Blank rows: try MULTIPLEXING 0/1/2/17 or check E address line (see comments).\n")

    matrix = make_matrix()

    try:
        print("Running tests — Ctrl-C to abort\n")
        test_solid_colors(matrix)
        test_gradient(matrix)
        test_checkerboard(matrix)
        test_border(matrix)
        test_pixel_walk(matrix)
        test_brightness_fade(matrix)
        print("\nAll tests complete.")
    except KeyboardInterrupt:
        print("\nAborted.")
    finally:
        matrix.Clear()


if __name__ == "__main__":
    main()
