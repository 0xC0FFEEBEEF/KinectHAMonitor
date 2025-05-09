
# KinectHAMonitor

**KinectHAMonitor** is a real-time motion-detection service that uses an **Xbox 360 Kinect (v1)** and Python to publish presence events to Home Assistant over MQTT.

It lets you …

- detect when a person enters or leaves a room  
- send `true / false` MQTT messages (with redundancy and debounce)  
- trigger lights or any other automations in Home Assistant

---

## Features

| Status | Feature |
| ------ | ------- |
| ✅ | Depth-based motion detection |
| ✅ | Debounce – motion only after 5 s of continuous activity |
| ✅ | Auto‑cooldown – `false` after 4 min of no motion |
| ✅ | Redundant MQTT message 30 s after each `true/false` |
| 🔜 | Gesture recognition (e.g. ✖ to turn off lights) |
| 🔜 | Auto‑tilt toward detected motion |

---

## MQTT Topics

| Topic           | Payload | Meaning                       |
| --------------- | ------- | ----------------------------- |
| `kinect/motion` | `true`  | Motion detected               |
| `kinect/motion` | `false` | No motion (after idle period) |

---

## Requirements

- **Python 3.10**  (3.11 / 3.12 will not compile the bindings)  
- Kinect v1 (Xbox 360)  
- [`libfreenect`](https://github.com/OpenKinect/libfreenect) + Python bindings  
- OpenCV, `paho‑mqtt`, and an MQTT broker (e.g. Mosquitto)  
- *(Optional)* Home Assistant with MQTT integration

---

## Project Structure
```
KinectHAMonitor/
├── Monitor/
│   └── kinect_motion_mqtt.py
├── kinectenv/              # Python 3.10 venv (git‑ignored)
├── libfreenect/            # source & build tree
└── README.md
```

---

## Optional – headless GUI testing (X‑forwarding)

```bash
sudo apt install xauth
ssh -Y user@SERVER_IP   # e.g.  ssh -Y crazycatlady@10.0.0.22
```

---
### Install Python 3.10 (Ubuntu 23/24 LTS)

Ubuntu Server 22.04+ ships Python 3.11 / 3.12 by default; libfreenect’s
bindings only compile on 3.10.  Install 3.10 side-by-side:

```bash
sudo apt update
sudo apt install software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.10 python3.10-venv python3.10-dev
```

---

## Installation

### 1  Clone the repo
```bash
cd ~
git clone https://github.com/0xC0FFEEBEEF/KinectHAMonitor.git
cd KinectHAMonitor
```

### 2  Create a **Python 3.10** virtual‑env
```bash
python3.10 -m venv kinectenv
source kinectenv/bin/activate
pip install --upgrade pip
pip install opencv-python paho-mqtt
```

### 3  Build **libfreenect** inside the venv  
*(Python 3.11/3.12 will fail – stay on 3.10)*
```bash
# System packages required for the build
sudo apt install cython3 git cmake build-essential                  libusb-1.0-0-dev python3.10-dev

# Python packages (still inside the venv)
pip install numpy setuptools cython paho-mqtt opencv-python

# Fetch and compile libfreenect
cd ~
git clone https://github.com/OpenKinect/libfreenect
cd libfreenect
mkdir build && cd build
cmake ..   -DBUILD_PYTHON3=ON   -DPYTHON_EXECUTABLE=$VIRTUAL_ENV/bin/python
make -j$(nproc)

# Copy the compiled module into the venv’s site‑packages
find wrappers/python -name "freenect*.so" -exec   cp {} $VIRTUAL_ENV/lib/python3.10/site-packages/ \;
```

---

## Running
```bash
cd ~/KinectHAMonitor/Monitor
source ../kinectenv/bin/activate      # should report Python 3.10.x
python3 kinect_motion_mqtt.py
```
You’ll see console messages such as “⚠️ Motion started” / “✅ No motion”.  
Subscribing to the topic:

```bash
mosquitto_sub -t kinect/motion
```
shows the matching `true / false` events.

---

## .gitignore recommendation
```
kinectenv/
libfreenect/build/
__pycache__/
*.pyc
```

Feel free to open an issue or PR if you improve gesture detection, auto‑tilt, or anything else!