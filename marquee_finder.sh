#!/bin/bash

# --- Configuration ---
DEFAULT_IMAGE="/home/pi/RetroPie/marquees/default.png"
PI2_USER="prioret"
PI2_HOST="192.168.1.107"
PI2_DEST="/tmp/marquee_incoming/current.png"
CHECK_INTERVAL=2
LOG_FILE="/var/log/marquee_finder.log"
# ---------------------

last_sent=""

log() {
    local level="$1"
    shift
    local msg="$*"
    local ts
    ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo "${ts} ${level} ${msg}" | tee -a "$LOG_FILE"
}

mkdir -p "$(dirname "$LOG_FILE")"
log INFO "marquee_finder starting"

get_marquee() {
    if ! pgrep -x "retroarch" > /dev/null; then
        echo "$DEFAULT_IMAGE"
        return
    fi

    local system_file="/tmp/current_system.txt"
    local rom_file="/tmp/current_rom.txt"

    if [[ ! -s "$system_file" || ! -s "$rom_file" ]]; then
        echo "$DEFAULT_IMAGE"
        return
    fi

    local system rom_path rom_name marquee
    system=$(cat "$system_file")
    rom_path=$(cat "$rom_file")
    rom_name=$(basename "${rom_path%.*}")
    marquee="/home/pi/RetroPie/roms/${system}/media/marquees/${rom_name}.png"

    if [[ -f "$marquee" ]]; then
        echo "$marquee"
    else
        log WARNING "Marquee not found for ${rom_name} (${system}), using default"
        echo "$DEFAULT_IMAGE"
    fi
}

send_to_pi2() {
    local file="$1"
    # SCP to a temp file then rename to avoid partial reads on Pi 2
    scp "$file" "${PI2_USER}@${PI2_HOST}:${PI2_DEST}.tmp" 2>/dev/null && \
        ssh "${PI2_USER}@${PI2_HOST}" "mv ${PI2_DEST}.tmp ${PI2_DEST}" 2>/dev/null
}

while true; do
    current=$(get_marquee)

    if [[ -n "$current" && -f "$current" && "$current" != "$last_sent" ]]; then
        log INFO "Sending $current to Pi 2"
        if send_to_pi2 "$current"; then
            log INFO "Sent $current"
            last_sent="$current"
        else
            log ERROR "Failed to send $current to Pi 2"
        fi
    fi

    sleep "$CHECK_INTERVAL"
done
