import freenect
import cv2
import numpy as np
import time

last_tilt = None
last_tilt_time = 0
TILT_COOLDOWN = 2.0  # seconds between tilt adjustments

# Future idea: replace direct tilt with queued targetTilt execution
target_tilt = None
motor_dev = None  # Will be set by main script


def compute_centroid(mask):
    moments = cv2.moments(mask)
    if moments['m00'] == 0:
        return None
    cx = int(moments['m10'] / moments['m00'])
    cy = int(moments['m01'] / moments['m00'])
    return (cx, cy)


def track_from_frame(frame: np.ndarray, _, debug: bool = False):
    global last_tilt, last_tilt_time, target_tilt, motor_dev

    if motor_dev is None:
        if debug:
            print("[ERROR] motor_dev is not initialized")
        return

    blurred = cv2.GaussianBlur(frame, (9, 9), 0)
    _, thresh = cv2.threshold(blurred, 15, 255, cv2.THRESH_BINARY)
    centroid = compute_centroid(thresh)

    if debug:
        print("[DEBUG] Tilt function active")
        if centroid:
            print(f"[DEBUG] Found centroid: {centroid}")
        else:
            print("[DEBUG] No centroid found")

    if centroid:
        _, y = centroid
        tilt = int(np.interp(y, [0, 480], [30, -30]))
        tilt = max(min(tilt, 30), -30)
        target_tilt = tilt

        now = time.time()
        if (now - last_tilt_time) > TILT_COOLDOWN:
            freenect.update_tilt_state(motor_dev)

            if debug:
                print(f"[DEBUG] Executing tilt move to {target_tilt}")

            poke = target_tilt + 1 if target_tilt < 30 else target_tilt - 1
            freenect.set_tilt_degs(motor_dev, poke)
            if debug:
                print(f"[DEBUG] Poked tilt to {poke}°")
            time.sleep(0.3)
            freenect.set_tilt_degs(motor_dev, target_tilt)
            if debug:
                print(f"[TILT] Forced adjust to {target_tilt}° from centroid y={y}")

            last_tilt = target_tilt
            last_tilt_time = now
    elif debug:
        print("[INFO] No motion centroid detected")


# Grace period feature: must be handled in caller (e.g. motion state logic)
MOTION_GRACE_PERIOD = 6.0  # seconds of sustained stillness before allowing 'false' state
