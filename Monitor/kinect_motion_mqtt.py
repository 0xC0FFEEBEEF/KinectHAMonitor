# kinect_motion_mqtt.py
import freenect
import cv2
import numpy as np
import paho.mqtt.client as mqtt
import time

# Config
MQTT_BROKER = "localhost"
MQTT_TOPIC = "kinect/motion"
MOTION_THRESHOLD = 1000000  
IDLE_TIME = 4 * 60          # 4 minutes in seconds
REDUNDANCY_DELAY = 30

client = mqtt.Client()
client.connect(MQTT_BROKER)

last_frame = None
last_motion_time = 0
motion_state = False
redundancy_sent = False
check_interval = 5  # seconds

def get_depth():
    depth, _ = freenect.sync_get_depth()
    return depth.astype(np.uint8)

def motion_detected(prev, current):
    diff = cv2.absdiff(current, prev)
    _, thresh = cv2.threshold(diff, 15, 255, cv2.THRESH_BINARY)
    return np.sum(thresh) > MOTION_THRESHOLD

while True:
    frame = get_depth()
    now = time.time()

    if last_frame is not None:
        if motion_detected(last_frame, frame):
            if not motion_state:
                print("⚠️ Motion started")
                motion_state = True
                last_motion_time = now
                redundancy_sent = False
                client.publish(MQTT_TOPIC, "true")
            elif now - last_motion_time > 5 and not redundancy_sent:
                print("📢 Redundant motion message")
                client.publish(MQTT_TOPIC, "true")
                redundancy_sent = True
            check_interval = 1
        else:
            if motion_state and now - last_motion_time > IDLE_TIME:
                print("✅ No motion")
                motion_state = False
                client.publish(MQTT_TOPIC, "false")
                time.sleep(REDUNDANCY_DELAY)
                client.publish(MQTT_TOPIC, "false")
                check_interval = 5

    last_frame = frame
    time.sleep(check_interval)
