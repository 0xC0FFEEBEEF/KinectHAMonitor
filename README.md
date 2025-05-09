# KinectHAMonitor

**KinectHAMonitor** is a real-time motion detection system using a Kinect sensor (Xbox 360) and Python to monitor presence and publish motion state updates to Home Assistant via MQTT.

This project is designed to:
- Detect when a person enters or leaves a room
- Communicate state changes (`true` / `false`) over MQTT
- Integrate directly into Home Assistant for automations

## Features

- ✅ Motion detection using Kinect depth data
- ✅ Smart debounce: only reports motion after 5 seconds of consistent presence
- ✅ Auto-cooldown: reports `false` after 4 minutes of no movement
- ✅ MQTT redundancy messaging for reliability
- 🔜 Planned: gesture recognition, auto-tilt based on motion direction

## MQTT Topics

| Topic            | Payload | Description                |
|------------------|---------|----------------------------|
| `kinect/motion`  | `true`  | Motion detected            |
| `kinect/motion`  | `false` | No motion (after timeout)  |

## Requirements

- Python 3.10+
- Kinect v1 (Xbox 360)
- [`libfreenect`](https://github.com/OpenKinect/libfreenect) with Python bindings
- OpenCV
- `paho-mqtt`
- An MQTT broker (e.g. Mosquitto)
- Optional: Home Assistant with MQTT integration

## Project Structure
KinectHAMonitor/
├── Monitor/
│ └── kinect_motion_mqtt.py
├── kinectenv/ # (venv - not committed)
├── libfreenect/ # (built from source)
└── README.md

## Installation

```bash
# Clone the repo
git clone https://github.com/0xC0FFEEBEEF/KinectHAMonitor.git
cd KinectHAMonitor
```
# Setup environment
```bash
python3 -m venv kinectenv
source kinectenv/bin/activate
pip install opencv-python paho-mqtt
```
# Build libfreenect manually (see official docs, notes below may not be reliable\\ working with ubuntuserver as of 05/09/25)
```bash
sudo apt install cython3 git cmake build-essential libusb-1.0-0-dev python3-full
pip install numpy setuptools paho-mqtt freenect opencv-python
pip install setuptools
git clone https://github.com/OpenKinect/libfreenect
cd libfreenect
mkdir build
cd build
cmake .. -DBUILD_PYTHON3=ON
make
```
## optional Build for headless gui testing
```bash
sudo apt install xauth
sudo reboot
ssh -Y x.x.x.x #x being your machines ip ex:ssh -Y 10.0.0.22
```

## Running
Make sure your environment is active:

```bash
cd Monitor
source ../kinectenv/bin/activate
python3 kinect_motion_mqtt.py

```


