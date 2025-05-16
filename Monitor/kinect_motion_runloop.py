import freenect, cv2, numpy as np, paho.mqtt.client as mqtt
import os, sys, argparse, configparser, itertools, time
from collections import deque
from typing import Optional

# --------------------------------------------------
# Spinner & silence libusb
# --------------------------------------------------
spinner = itertools.cycle(["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"])
os.dup2(os.open(os.devnull, os.O_RDWR), 2)

# --------------------------------------------------
# Config & CLI
# --------------------------------------------------
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.conf")
cfg = configparser.ConfigParser()
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH) as f:
        cfg.read_string("[DEFAULT]\n" + f.read())
d = cfg['DEFAULT'] if 'DEFAULT' in cfg else {}

p = argparse.ArgumentParser("Kinect motion + jog-tilt + MQTT")
p.add_argument('--broker',    default=d.get('BROKER','localhost'))
p.add_argument('--topic',     default=d.get('TOPIC','kinect/motion'))
p.add_argument('--threshold', type=int, default=int(d.get('THRESHOLD',3_000_000)))
p.add_argument('--quiet',     action='store_true',
               default=d.get('QUIET','false').lower()=='true')
p.add_argument('--debug',     action='store_true')
p.add_argument('--display',   action='store_true')
ARGS = p.parse_args()
dbg = print if ARGS.debug else (lambda *a,**k: None)

MQTT_USER = d.get("MQTT_USER") or os.getenv("MQTT_USER")
MQTT_PASS = d.get("MQTT_PASS") or os.getenv("MQTT_PASS")

# --------------------------------------------------
# Windows if requested
# --------------------------------------------------
if ARGS.display:
    cv2.namedWindow("Depth",  cv2.WINDOW_NORMAL)
    cv2.namedWindow("Motion", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Depth",  480, 360)
    cv2.resizeWindow("Motion", 480, 360)

# --------------------------------------------------
# MQTT helper
# --------------------------------------------------
client: Optional[mqtt.Client] = None
def connect_mqtt():
    c = mqtt.Client(protocol=mqtt.MQTTv311)
    if MQTT_USER and MQTT_PASS:
        c.username_pw_set(MQTT_USER, MQTT_PASS)
    c.connect(ARGS.broker); c.loop_start()
    if not ARGS.quiet:
        print(f"🛰️ MQTT → {ARGS.broker}")
    return c
def publish(v): client.publish(ARGS.topic, v, retain=False)

# --------------------------------------------------
# Globals
# --------------------------------------------------
pixel_hist            = deque(maxlen=30)
CHECK_INTERVAL        = 5.0
last_check            = 0.0
motion_state          = False
last_motion           = 0.0
DEBOUNCE_SEC          = 5
IDLE_TIMEOUT          = 4*60
MOTION_GRACE_EVALS    = 30
below_cnt             = 0
TILT_COOLDOWN         = 1.0        # faster with jogs
last_tilt_time        = 0.0
STEP_DEG              = 5           # one jog = 5°
current_tilt          = -15         # start slightly down
LED_GREEN, LED_RED    = 1, 2
desired_led, last_led = LED_GREEN, None

# --------------------------------------------------
# Helpers
# --------------------------------------------------
def centroid_y(mask: np.ndarray):
    m = cv2.moments(mask)
    return None if m['m00'] == 0 else int(m['m01'] / m['m00'])

# --------------------------------------------------
# Depth callback
# --------------------------------------------------
def process_depth(dev, depth, ts):
    global last_check, motion_state, last_motion, below_cnt
    global desired_led, current_tilt, last_tilt_time

    print(f"\rMonitoring… {next(spinner)}", end='', flush=True)

    frame = depth.astype(np.uint8)

    if process_depth.prev is not None:
        diff = cv2.absdiff(frame, process_depth.prev)
        _, msk = cv2.threshold(diff, 15, 255, cv2.THRESH_BINARY)
        pixel_hist.append(int(msk.sum()))

        if ARGS.display:
            cv2.imshow("Depth",  cv2.applyColorMap(frame, cv2.COLORMAP_OCEAN))
            cv2.imshow("Motion", msk)
            cv2.waitKey(1)

        if motion_state:
            px_sum = int(msk.sum())
            cy     = centroid_y(msk)
            if cy is not None:
                h = frame.shape[0]
                if cy < h*0.30 and px_sum > ARGS.threshold:
                    current_tilt = min(current_tilt + STEP_DEG,  30)   # jog UP
                    dbg(f"[JOG] up   → {current_tilt}°  px={px_sum}")
                elif cy > h*0.70 and px_sum > ARGS.threshold:
                    current_tilt = max(current_tilt - STEP_DEG, -30)   # jog DOWN
                    dbg(f"[JOG] down → {current_tilt}°  px={px_sum}")

    process_depth.prev = frame

    # ---- motion evaluation every 5 s ----
    now = time.time()
    if now - last_check < CHECK_INTERVAL:
        return
    last_check = now

    if not pixel_hist:
        return
    avg = sum(pixel_hist)/len(pixel_hist)
    pixel_hist.clear()
    dbg(f"[EVAL] avg={int(avg)} thr={ARGS.threshold}")

    if avg > ARGS.threshold:
        below_cnt = 0
        if not motion_state:
            if not ARGS.quiet:
                print("⚠️ Motion started")
            publish('true')
            motion_state = True
            last_motion  = now
            desired_led  = LED_RED
        elif now - last_motion > DEBOUNCE_SEC:
            publish('true'); last_motion = now
    else:
        if motion_state:
            below_cnt += 1
            if below_cnt >= MOTION_GRACE_EVALS or now-last_motion >= IDLE_TIMEOUT:
                if not ARGS.quiet:
                    print("✅ Motion ended")
                publish('false')
                motion_state = False
                desired_led  = LED_GREEN
        else:
            below_cnt = 0

process_depth.prev = None

# --------------------------------------------------
# Body callback
# --------------------------------------------------
def body_callback(dev, ctx):
    global last_led, last_tilt_time
    now = time.time()
    if desired_led != last_led:
        freenect.set_led(dev, desired_led); last_led = desired_led
    if now - last_tilt_time >= TILT_COOLDOWN:
        freenect.update_tilt_state(dev)
        freenect.set_tilt_degs(dev, current_tilt)
        last_tilt_time = now

# --------------------------------------------------
# Main
# --------------------------------------------------
if __name__ == '__main__':
    if ARGS.display:
        cv2.namedWindow("Depth"); cv2.namedWindow("Motion")
    client = connect_mqtt()
    try:
        freenect.runloop(depth=process_depth, body=body_callback)
    except KeyboardInterrupt:
        print("\nInterrupted – exiting")
    finally:
        if ARGS.display: cv2.destroyAllWindows()
        sys.exit(0)
