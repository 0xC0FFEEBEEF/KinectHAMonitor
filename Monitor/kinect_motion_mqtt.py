from __future__ import annotations
import argparse
import os
import sys
sys.stderr.flush()
devnull = os.open(os.devnull, os.O_RDWR)
os.dup2(devnull, 2)
import time
import itertools
import configparser
from typing import Optional
from collections import deque

spin_cycle = itertools.cycle('|/-\\')
quiet_mode = "--quiet" in sys.argv

if quiet_mode:
    devnull_fd = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull_fd, 2)

import cv2
import freenect
import numpy as np
import paho.mqtt.client as mqtt

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.conf")

config = configparser.ConfigParser()
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH) as f:
        raw = f.read()
    raw = "[DEFAULT]\n" + raw
    config.read_string(raw)
else:
    config['DEFAULT'] = {}

defaults = config['DEFAULT']
MQTT_USER = defaults.get("MQTT_USER") or os.getenv("MQTT_USER")
MQTT_PASS = defaults.get("MQTT_PASS") or os.getenv("MQTT_PASS")

def get_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kinect → MQTT motion bridge")
    p.add_argument("--broker", default=defaults.get("BROKER"), help="MQTT broker IP or hostname")
    p.add_argument("--topic", default=defaults.get("TOPIC", "kinect/motion"), help="MQTT topic for motion state")
    p.add_argument("--threshold", type=int, default=int(defaults.get("THRESHOLD", 3000000)), help="Pixel-sum threshold that counts as motion")
    p.add_argument("--quiet", action="store_true", default=defaults.get("QUIET", "false").lower() == "true", help="Suppress motion logging output")
    p.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = p.parse_args()
    if not args.broker:
        args.broker = input("Enter MQTT broker IP or hostname [default: localhost]: ").strip() or "localhost"
    return args

ARGS = get_args()

IDLE_TIME = 4 * 60
REDUNDANCY_DELAY = 30
DEBOUNCE_SEC = 5

def connect_mqtt(broker: str) -> mqtt.Client:
    client = mqtt.Client(protocol=mqtt.MQTTv311)
    if MQTT_USER and MQTT_PASS:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
    for retry in range(5):
        try:
            client.connect(broker)
            client.loop_start()
            if not ARGS.quiet:
                print(f"🛰️  Connected to MQTT broker @ {broker}")
            return client
        except OSError as e:
            print(f"MQTT connect failed ({e}); retrying in 5 seconds |!| attempt ({retry + 1}/5)")
            time.sleep(5)
    print("\nExiting after 5 attempts… check your config or broker.")
    sys.exit(1)

def publish_state(client: mqtt.Client, topic: str, state: str) -> None:
    client.publish(topic, state, retain=False)

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

def get_depth_frame() -> Optional[np.ndarray]:
    try:
        depth, _ = freenect.sync_get_depth()
        if depth is None:
            return None
        return depth.astype(np.uint8)
    except Exception as e:
        print(f"[ERROR] Failed to get depth frame: {e}")
        return None

def motion_pixel_sum(prev: np.ndarray, cur: np.ndarray) -> int:
    diff = cv2.absdiff(cur, prev)
    _, msk = cv2.threshold(diff, 15, 255, cv2.THRESH_BINARY)
    return int(msk.sum())

# Deque holds the last 30 pixel sums
pixel_history = deque(maxlen=30)

def smoothed_motion(current_sum: int, threshold: int) -> bool:
    pixel_history.append(current_sum)
    avg = sum(pixel_history) / len(pixel_history)
    if ARGS.debug:
        print(f"[DEBUG] Motion pixel sum: {current_sum} | Avg: {int(avg)} (threshold: {threshold})")
    return avg > threshold

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
        if frame is None:
            time.sleep(1)
            continue

        now = time.time()
        if last_frame is not None:
            pixel_sum = motion_pixel_sum(last_frame, frame)

            if smoothed_motion(pixel_sum, ARGS.threshold):
                if not motion_state:
                    if not ARGS.quiet:
                        print("⚠️  Motion started")
                    motion_state = True
                    last_motion = now
                    redundant_sent = False
                    print(f"[MQTT] Publishing 'true' to {ARGS.topic}")
                    publish_state(client, ARGS.topic, "true")
                elif (now - last_motion > DEBOUNCE_SEC) and not redundant_sent:
                    if not ARGS.quiet:
                        print("📢 Redundant motion message")
                    print(f"[MQTT] Publishing 'true' to {ARGS.topic}")    
                    publish_state(client, ARGS.topic, "true")
                    redundant_sent = True
                interval = 5.0
            else:
                # If all recent frames are under threshold, declare no motion
                if motion_state and len(pixel_history) == pixel_history.maxlen and all(s < ARGS.threshold for s in pixel_history):
                    if not ARGS.quiet:
                        print("✅ No motion")
                    motion_state = False
                    print(f"[MQTT] Publishing 'false' to {ARGS.topic}")

                    publish_state(client, ARGS.topic, "false")
                    #time.sleep(REDUNDANCY_DELAY)
                    print(f"[MQTT] Publishing 'false' to {ARGS.topic}")

                    publish_state(client, ARGS.topic, "false")
                    interval = 5.0


        last_frame = frame
        if ARGS.quiet:
            print(f"\rMonitoring… {next(spin_cycle)}", end="", flush=True)
        print(f"\rMonitoring… {next(spin_cycle)}", end="", flush=True)
        time.sleep(interval)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted – shutting down.")
        sys.exit(0)
