#!/bin/bash

# Check if retroarch is actually running
if ! pgrep -x "retroarch" > /dev/null; then
    echo "ERROR: No game is currently running." >&2
    exit 1
fi

SYSTEM=$(cat /tmp/current_system.txt)
ROM_PATH=$(cat /tmp/current_rom.txt)

# Validate they aren't empty
if [ -z "$SYSTEM" ] || [ -z "$ROM_PATH" ]; then
    echo "ERROR: Could not read game info." >&2
    exit 1
fi

# Get just the rom filename without extension
ROM_NAME=$(basename "${ROM_PATH%.*}")

# Build marquee path using Skyscraper's media folder structure
MARQUEE_PATH="/home/pi/RetroPie/roms/${SYSTEM}/media/marquees/${ROM_NAME}.png"

if [ ! -f "$MARQUEE_PATH" ]; then
    echo "ERROR: Marquee file not found: $MARQUEE_PATH" >&2
    exit 1
fi

echo "$MARQUEE_PATH"
