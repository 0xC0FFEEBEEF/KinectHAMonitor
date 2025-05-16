import freenect
import cv2
import numpy as np
import paho.mqtt.client as mqtt
import os, sys, argparse, configparser, itertools, time
from collections import deque
from typing import Optional

# --------------------------------------------------
# Spinner & Console Suppression
# --------------------------------------------------
spinner_frames = [
    "[96m⠋[0m", "[96m⠙[0m", "[96m⠹[0m", "[96m⠸[0m",
    "[96m⠼[0m", "[96m⠴[0m", "[96m⠦[0m", "[96m⠧[0m",
    "[96m⠇[0m", "[96m⠏[0m"
]
spin_cycle = itertools.cycle(spinner_frames)
# --------------------------------------------------
# Config & CLI Args
# --------------------------------------------------
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.conf")
config = configparser.ConfigParser()
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH) as f:
        raw = "[DEFAULT]\n" + f.read()
    config.read_string(raw)

defaults = config['DEFAULT'] if 'DEFAULT' in config else {}

MQTT_USER = defaults.get("MQTT_USER") or os.getenv("MQTT_USER")
MQTT_PASS = defaults.get("MQTT_PASS") or os.getenv("MQTT_PASS")

parser = argparse.ArgumentParser(description="Kinect motion + tilt + MQTT + LED (legacy timing)")
parser.add_argument('--broker', default=defaults.get('BROKER', 'localhost'))
parser.add_argument('--topic',  default=defaults.get('TOPIC',  'kinect/motion'))
parser.add_argument('--threshold', type=int, default=int(defaults.get('THRESHOLD', 3_000_000)))
parser.add_argument('--quiet', action='store_true', default=defaults.get('QUIET', 'false').lower() == 'true')
parser.add_argument('--debug', action='store_true')
ARGS = parser.parse_args()

# --------------------------------------------------
# MQTT helper
# --------------------------------------------------
client: Optional[mqtt.Client] = None

def connect_mqtt() -> mqtt.Client:
    c = mqtt.Client(protocol=mqtt.MQTTv311)
    if MQTT_USER and MQTT_PASS:
        c.username_pw_set(MQTT_USER, MQTT_PASS)
    c.connect(ARGS.broker)
    c.loop_start()
    if not ARGS.quiet:
        print(f"🛰️  MQTT connected -> {ARGS.broker}")
    return c

def publish(state: str):
    client.publish(ARGS.topic, state, retain=False)

# --------------------------------------------------
# Globals (motion / timing)
# --------------------------------------------------
pixel_history = deque(maxlen=30)  # same length as original script
CHECK_INTERVAL = 5.0              # seconds between motion evaluations (legacy)
last_check = 0.0                  # wall‑clock timestamp of last evaluation

motion_state = False
last_motion = 0.0
DEBOUNCE_SEC = 5                  # redundant true after 5 s
IDLE_TIMEOUT = 4*60               # force false after 4 min

MOTION_GRACE_FRAME_COUNT = 30     # need 30 consecutive below‑threshold at eval time
below_counter = 0                 # counts consecutive evaluations below threshold

# Tilt + LED state remain unchanged
TILT_COOLDOWN = 2.0
last_tilt_time = 0
target_tilt = None

LED_GREEN, LED_RED, LED_YELLOW = 1, 2, 3
last_led = None
desired_led = LED_GREEN

# --------------------------------------------------
# Helper
# --------------------------------------------------
def compute_centroid(mask: np.ndarray):
    m = cv2.moments(mask)
    if m['m00'] == 0:
        return None
    return int(m['m10']/m['m00']), int(m['m01']/m['m00'])

# --------------------------------------------------
# Depth callback
# --------------------------------------------------

def process_depth(dev, depth, ts):
    global last_check, below_counter, motion_state, last_motion, desired_led, target_tilt

    # collect frame sums every frame
    frame = depth.astype(np.uint8)
    if process_depth.prev is not None:
        diff = cv2.absdiff(frame, process_depth.prev)
        _, msk = cv2.threshold(diff, 15, 255, cv2.THRESH_BINARY)
        pixel_history.append(int(msk.sum()))
    process_depth.prev = frame

    now = time.time()
    if now - last_check < CHECK_INTERVAL:
        return  # skip until next evaluation
    last_check = now

    if len(pixel_history) == 0:
        return
    avg = sum(pixel_history)/len(pixel_history)
    if ARGS.debug:
        print(f"[DEBUG] eval avg={int(avg)} th={ARGS.threshold}")
    pixel_history.clear()

    if avg > ARGS.threshold:  # motion detected at this evaluation
        below_counter = 0
        if not motion_state:
            if not ARGS.quiet:
                print("⚠️  Motion started")
            publish('true')
            motion_state = True
            last_motion = now
            desired_led = LED_RED
        elif now-last_motion > DEBOUNCE_SEC:
            publish('true')  # redundant true
            last_motion = now
        # update tilt target once per evaluation
        c = compute_centroid(msk)
        if c:
            _, y = c
            target_tilt = max(min(int(np.interp(y, [0, frame.shape[0]], [30, -30])), 30), -30)
    else:  # below threshold this eval
        if motion_state:
            below_counter += 1
            if below_counter >= MOTION_GRACE_FRAME_COUNT or now-last_motion >= IDLE_TIMEOUT:
                if not ARGS.quiet:
                    print("✅ Motion ended")
                publish('false')
                motion_state = False
                desired_led = LED_GREEN
        else:
            below_counter = 0
    print(f"\rMonitoring… {next(spin_cycle)}", end='', flush=True)

process_depth.prev = None

# --------------------------------------------------
# Body callback (tilt & LED)
# --------------------------------------------------

def body_callback(dev, ctx):
    global last_tilt_time, last_led
    now = time.time()
    if desired_led != last_led:
        freenect.set_led(dev, desired_led)
        last_led = desired_led
    if target_tilt is not None and now-last_tilt_time >= TILT_COOLDOWN:
        freenect.update_tilt_state(dev)
        freenect.set_tilt_degs(dev, target_tilt)
        last_tilt_time = now

# --------------------------------------------------
# Main
# --------------------------------------------------
if __name__ == '__main__':
    client = connect_mqtt()
    try:
        freenect.runloop(depth=process_depth, body=body_callback)
    except KeyboardInterrupt:
        print("\nInterrupted – exiting")
        sys.exit(0)
