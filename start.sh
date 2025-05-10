#!/bin/bash

cd "$(dirname "$0")"

# Ensure config.conf exists
if [ ! -f config.conf ]; then
    cp config.example.conf config.conf
    echo "✅ Created config.conf from default."
fi

# Load config
source config.conf

# Convert config values to CLI args
ARGS=""
[ "$QUIET" == "true" ] && ARGS+=" --quiet"
[ -n "$BROKER" ] && ARGS+=" --broker $BROKER"
[ -n "$TOPIC" ] && ARGS+=" --topic $TOPIC"
[ -n "$THRESHOLD" ] && ARGS+=" --threshold $THRESHOLD"

echo "🔁 Checking for updates..."
git reset --hard HEAD >/dev/null 2>&1
git pull origin main >/dev/null 2>&1
echo "✅ Repo is up to date."

# Activate venv & run script
source kinectenv/bin/activate
cd Monitor
exec python3 kinect_motion_mqtt.py $ARGS
