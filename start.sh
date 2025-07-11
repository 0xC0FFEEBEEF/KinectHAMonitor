#!/bin/bash
set -e

cd "$(dirname "$0")"

# Parse extra CLI flags (e.g. --debug)
EXTRA_ARGS="$@"
DEBUG_MODE=false
for arg in "$@"; do
  if [[ "$arg" == "--debug" ]]; then
    EXTRA_ARGS+=" --debug"
    DEBUG_MODE=true
  fi
done

# 1) Check for updates
echo "🔁 Checking for updates..."
git fetch origin main >/dev/null 2>&1
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
if [ "$LOCAL" = "$REMOTE" ]; then
    echo "✅ Repo is up to date."
else
    echo "🚨 Update available!"
    read -p "Would you like to pull the latest changes? (y/N): " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        git reset --hard HEAD
        git pull origin main
        echo "✅ Update pulled successfully."
    else
        echo "❌ Skipped update."
    fi
fi

# 2) Bootstrap config.conf
if [ ! -f config.conf ]; then
  if [ -f config.example.conf ]; then
    cp config.example.conf config.conf
    echo "✅ Created config.conf from default."
  else
    echo "⚠️  config.example.conf missing. Creating config.conf interactively..."

    read -p "Enter MQTT broker IP or hostname [default: localhost]: " BROKER
    BROKER=${BROKER:-localhost}

    read -p "Does your MQTT broker require authentication? (y/N): " auth_required
    if [[ "$auth_required" =~ ^[Yy]$ ]]; then
      read -p "Enter MQTT username: " MQTT_USER
      read -s -p "Enter MQTT password: " MQTT_PASS
      echo ""
    fi

    cat <<EOF > config.conf
# Generated config.conf
BROKER=$BROKER
TOPIC=kinect/motion
THRESHOLD=8000000
QUIET=true
EOF

    if [[ "$auth_required" =~ ^[Yy]$ ]]; then
      echo "MQTT_USER=$MQTT_USER" >> config.conf
      echo "MQTT_PASS=$MQTT_PASS" >> config.conf
      echo "✅ Added MQTT_USER and MQTT_PASS to config.conf"
    fi

    echo "✅ Created config.conf with entered broker ($BROKER)."
  fi
fi

# 3) Load config
source config.conf

# 4) Build CLI args
ARGS=""
[ "$QUIET" == "true" ]   && ARGS+=" --quiet"
[ -n "$BROKER" ]         && ARGS+=" --broker $BROKER"
[ -n "$TOPIC" ]          && ARGS+=" --topic $TOPIC"
[ -n "$THRESHOLD" ]      && ARGS+=" --threshold $THRESHOLD"
ARGS+=$EXTRA_ARGS

# 5) Ensure and activate virtualenv
if [ ! -d "kinectenv" ]; then
  echo "💠 Creating virtual environment..."
  python3.10 -m venv kinectenv
fi
source kinectenv/bin/activate

# 6) Launch the runloop version (default)
cd Monitor
export FREENECT_LOGLEVEL=none
while true; do
  if [ "$DEBUG_MODE" = true ]; then
    echo "🔎 Launching in DEBUG mode"
  fi
  python3 kinect_motion_runloop.py $ARGS
  echo "⚠️  Script crashed with code $? – restarting in 5 seconds..."
  sleep 5
done
