#!/usr/bin/env python3
"""
KinectHAMonitor – depth-based motion → MQTT bridge
-------------------------------------------------
• Uses libfreenect to grab depth frames
• Detects motion by simple frame differencing
• Publishes `true / false` to MQTT with redundancy and debounce
"""

from __future__ import annotations
import argparse
import os
import sys
import time
import itertools
from typing import Optional

# -- Handle --quiet *before* freenect is imported
spin_cycle = itertools.cycle('|/-\\')
quiet_mode = "--quiet" in sys.argv

if quiet_mode:
    devnull_fd = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull_fd, 2)  # Redirect C-level stderr to /dev/null

import cv2
import freenect
import numpy as np
import paho.mqtt.client as mqtt

# --------------------------------------------------------------------------- #
# CLI / configuration
# --------------------------------------------------------------------------- #
def get_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kinect → MQTT motion bridge")
    p.add_argument("--broker", default=None, help="MQTT broker IP or hostname")
    p.add_argument("--topic", default=os.getenv("MQTT_TOPIC", "kinect/motion"),
                   help="MQTT topic for motion state")
    p.add_argument("--threshold", type=int,
                   default=int(os.getenv("MOTION_THRESHOLD", 1_000_000)),
                   help="Pixel-sum threshold that counts as motion")
    p.add_argument("--quiet", action="store_true", help="Suppress motion logging output")
    args = p.parse_args()

    if not args.broker:
        args.broker = input("Enter MQTT broker IP or hostname [default: localhost]: ").strip() or "localhost"
    return args

ARGS = get_args()

# timing constants
IDLE_TIME        = 4 * 60
REDUNDANCY_DELAY = 30
DEBOUNCE_SEC     = 5

# --------------------------------------------------------------------------- #
# MQTT setup
# --------------------------------------------------------------------------- #
def connect_mqtt(broker: str) -> mqtt.Client:
    client = mqtt.Client(protocol=mqtt.MQTTv311)
    while True:
        try:
            client.connect(broker)
            if not ARGS.quiet:
                print(f"🛰️  Connected to MQTT broker @ {broker}")
            return client
        except OSError as e:
            print(f"MQTT connect failed ({e}); retrying in 10 s …")
            time.sleep(10)

def publish_state(client: mqtt.Client, topic: str, state: str) -> None:
    client.publish(topic, state, retain=False)
    
# --------------------------------------------------------------------------- #
# HA Auto Discovery
# --------------------------------------------------------------------------- #
def publish_autodiscovery(client: mqtt.Client, topic: str) -> None:
    discovery_topic = "homeassistant/binary_sensor/kinect_motion/config"
    payload = {
        "name": "Kinect Motion",
        "state_topic": topic,
        "device_class": "motion",
        "payload_on": "true",
        "payload_off": "false",
        "unique_id": "kinect_motion_01",
        "device": {
            "identifiers": ["kinect_hamonitor"],
            "name": "Kinect HAMonitor",
            "manufacturer": "OpenKinect",
            "model": "Xbox 360 Kinect"
        }
    }

    import json
    client.publish(discovery_topic, json.dumps(payload), retain=True)


# --------------------------------------------------------------------------- #
# Kinect logic
# --------------------------------------------------------------------------- #
def get_depth_frame() -> np.ndarray:
    depth, _ = freenect.sync_get_depth()
    return depth.astype(np.uint8)

def motion_detected(prev: np.ndarray, cur: np.ndarray, threshold: int) -> bool:
    diff = cv2.absdiff(cur, prev)
    _, msk = cv2.threshold(diff, 15, 255, cv2.THRESH_BINARY)
    return int(msk.sum()) > threshold

# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #
def main() -> None:
    client = connect_mqtt(ARGS.broker)
    publish_autodiscovery(client, ARGS.topic)
    last_frame: Optional[np.ndarray] = None
    last_motion = 0.0
    motion_state = False
    redundant_sent = False
    interval = 5.0


    while True:
        frame = get_depth_frame()
        now = time.time()

        if last_frame is not None:
            if motion_detected(last_frame, frame, ARGS.threshold):
                if not motion_state:
                    if not ARGS.quiet:
                        print("⚠️  Motion started")
                    motion_state = True
                    last_motion = now
                    redundant_sent = False
                    publish_state(client, ARGS.topic, "true")

                elif (now - last_motion > DEBOUNCE_SEC) and not redundant_sent:
                    if not ARGS.quiet:
                        print("📢 Redundant motion message")
                    publish_state(client, ARGS.topic, "true")
                    redundant_sent = True

                interval = 1.0
            else:
                if motion_state and (now - last_motion > IDLE_TIME):
                    if not ARGS.quiet:
                        print("✅ No motion")
                    motion_state = False
                    publish_state(client, ARGS.topic, "false")
                    time.sleep(REDUNDANCY_DELAY)
                    publish_state(client, ARGS.topic, "false")
                    interval = 5.0

        last_frame = frame

        if ARGS.quiet:
            print(f"\rMonitoring… {next(spin_cycle)}", end="", flush=True)

        time.sleep(interval)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted – shutting down.")
        sys.exit(0)
