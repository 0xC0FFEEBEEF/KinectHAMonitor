#!/bin/bash

cd "$(dirname "$0")"

# Ensure config.conf exists
if [ ! -f config.conf ]; then
  if [ -f config.example.conf ]; then
    cp config.example.conf config.conf
    echo "✅ Created config.conf from default."
  else
    echo "⚠️  config.example.conf missing. Creating config.conf interactively..."

    # Prompt user for broker and write full config.conf
    read -p "Enter MQTT broker IP or hostname [default: localhost]: " BROKER
    BROKER=${BROKER:-localhost}
    cat <<EOF > config.conf
# Generated config.conf
BROKER="$BROKER"
TOPIC="kinect/motion"
THRESHOLD="1000000"
QUIET="true"
EOF
    echo "✅ Created config.conf with entered broker ($BROKER)."
  fi
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
