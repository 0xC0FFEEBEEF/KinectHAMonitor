#!/usr/bin/env python3
"""
KinectHAMonitor – depth-based motion → MQTT bridge
-------------------------------------------------

•   Uses libfreenect to grab depth frames
•   Detects motion by simple frame differencing
•   Publishes `true / false` to MQTT with redundancy and debounce
"""

from __future__ import annotations
import argparse
import os
import sys
import time
from typing import Optional

import cv2
import freenect
import numpy as np
import paho.mqtt.client as mqtt

# --------------------------------------------------------------------------- #
# CLI / configuration
# --------------------------------------------------------------------------- #
def get_args() -> argparse.Namespace:
    default_broker = os.getenv("MQTT_BROKER", "").strip()
    if not default_broker:
        default_broker = input("Enter MQTT broker IP or hostname [default: localhost]: ").strip() or "localhost"

    p = argparse.ArgumentParser(description="Kinect → MQTT motion bridge")
    p.add_argument("--broker", default=default_broker,
                   help="MQTT broker host/IP (default: localhost or env MQTT_BROKER)")
    p.add_argument("--topic", default=os.getenv("MQTT_TOPIC", "kinect/motion"),
                   help="MQTT topic for motion state")
    p.add_argument("--threshold", type=int,
                   default=int(os.getenv("MOTION_THRESHOLD", 1_000_000)),
                   help="Pixel-sum threshold that counts as motion")
    return p.parse_args()



ARGS = get_args()

# timing / logic constants
IDLE_TIME        = 4 * 60          # seconds of no motion → publish false
REDUNDANCY_DELAY = 30              # second confirm msg
DEBOUNCE_SEC     = 5               # continuous motion before redundant true


# --------------------------------------------------------------------------- #
# MQTT helper – keep retrying until broker is available
# --------------------------------------------------------------------------- #
def connect_mqtt(broker: str) -> mqtt.Client:
    client = mqtt.Client(protocol=mqtt.MQTTv311)
    while True:
        try:
            client.connect(broker)
            print(f"🛰️  Connected to MQTT broker @ {broker}")
            return client
        except OSError as e:
            print(f"MQTT connect failed ({e}); retrying in 10 s …")
            time.sleep(10)


def publish_state(client: mqtt.Client, topic: str, state: str) -> None:
    client.publish(topic, state, retain=False)


# --------------------------------------------------------------------------- #
# Kinect helpers
# --------------------------------------------------------------------------- #
def get_depth_frame() -> np.ndarray:
    depth, _ = freenect.sync_get_depth()
    return depth.astype(np.uint8)


def motion_detected(prev: np.ndarray,
                    cur: np.ndarray,
                    threshold: int) -> bool:
    diff   = cv2.absdiff(cur, prev)
    _, msk = cv2.threshold(diff, 15, 255, cv2.THRESH_BINARY)
    return int(msk.sum()) > threshold


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #
def main() -> None:
    client = connect_mqtt(ARGS.broker)

    last_frame:   Optional[np.ndarray] = None
    last_motion   = 0.0
    motion_state  = False
    redundant_sent = False
    interval      = 5.0   # seconds between polls

    while True:
        frame = get_depth_frame()
        now   = time.time()

        if last_frame is not None:
            if motion_detected(last_frame, frame, ARGS.threshold):
                # ----------------------------------------------------------------
                if not motion_state:          # rising edge
                    print("⚠️  Motion started")
                    motion_state   = True
                    last_motion    = now
                    redundant_sent = False
                    publish_state(client, ARGS.topic, "true")

                elif (now - last_motion > DEBOUNCE_SEC) and not redundant_sent:
                    print("📢 Redundant motion message")
                    publish_state(client, ARGS.topic, "true")
                    redundant_sent = True

                interval = 1.0

            # -----------------------------  no motion in this frame -------------
            else:
                if motion_state and (now - last_motion > IDLE_TIME):
                    print("✅ No motion")
                    motion_state = False
                    publish_state(client, ARGS.topic, "false")
                    time.sleep(REDUNDANCY_DELAY)
                    publish_state(client, ARGS.topic, "false")
                    interval = 5.0

        last_frame = frame
        time.sleep(interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted – shutting down.")
        sys.exit(0)
