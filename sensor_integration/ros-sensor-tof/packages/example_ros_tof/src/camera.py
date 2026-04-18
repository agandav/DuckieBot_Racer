#!/usr/bin/env python3
"""
camera.py — Split-frame color detection for DuckieBot racer
Runs on the robot inside Docker container, reads from ROS camera topic.

get_camera_color()    → "red" | "yellow" | "green" | "none"
get_yellow_position() → "left" | "right" | "center"
"""

import cv2
import numpy as np
import threading

# ROS imports — available inside Docker container
import rospy
from sensor_msgs.msg import CompressedImage
from turbojpeg import TurboJPEG

# ─────────────────────────────────────────────────────────────────────────────
# HSV color ranges
# ─────────────────────────────────────────────────────────────────────────────
RED_LOWER_1 = np.array([0,   150, 70])
RED_UPPER_1 = np.array([8,   255, 255])
RED_LOWER_2 = np.array([170, 150, 70])
RED_UPPER_2 = np.array([180, 255, 255])

YELLOW_LOWER = np.array([18, 80, 80])
YELLOW_UPPER = np.array([35, 255, 255])

WHITE_LOWER = np.array([0,   0,   180])
WHITE_UPPER = np.array([180, 40,  255])

GREEN_LOWER = np.array([40, 80, 80])
GREEN_UPPER = np.array([80, 255, 255])

# ─────────────────────────────────────────────────────────────────────────────
# Pixel thresholds — tune on actual robot
# ─────────────────────────────────────────────────────────────────────────────
RED_THRESHOLD_TOP    = 300
RED_THRESHOLD_BOTTOM = 500
YELLOW_THRESHOLD     = 800
WHITE_THRESHOLD      = 1000
GREEN_THRESHOLD      = 300
YELLOW_ZONE_MIN      = 300

# ─────────────────────────────────────────────────────────────────────────────
# ROS camera subscriber — runs in background thread
# ─────────────────────────────────────────────────────────────────────────────
jpeg         = TurboJPEG()
_latest_frame = None
_frame_lock   = threading.Lock()
_initialized  = False

def _camera_callback(msg: CompressedImage):
    global _latest_frame
    try:
        frame = jpeg.decode(msg.data)
        with _frame_lock:
            _latest_frame = frame
    except Exception as e:
        print(f"[CAM] Decode error: {e}")

def init_camera():
    """
    Subscribe to robot camera topic.
    Call once at startup before using get_frame().
    Safe to call multiple times — only initializes once.
    """
    global _initialized
    if _initialized:
        return
    try:
        rospy.init_node('camera_detector', anonymous=True, disable_signals=True)
    except rospy.exceptions.ROSException:
        pass  # node already initialized
    rospy.Subscriber(
        "/duckiebot18/camera_node/image/compressed",
        CompressedImage,
        _camera_callback,
        buff_size=4*1024*1024,
        queue_size=1
    )
    _initialized = True
    print("[CAM] Subscribed to robot camera topic")

def get_frame() -> np.ndarray | None:
    """Returns latest frame from robot camera."""
    init_camera()
    with _frame_lock:
        if _latest_frame is None:
            print("[CAM] No frame yet")
            return None
        return _latest_frame.copy()

# ─────────────────────────────────────────────────────────────────────────────
# Color detection
# ─────────────────────────────────────────────────────────────────────────────
def detect_color_in_region(region: np.ndarray) -> dict:
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    red_mask = (
        cv2.inRange(hsv, RED_LOWER_1, RED_UPPER_1) |
        cv2.inRange(hsv, RED_LOWER_2, RED_UPPER_2)
    )
    yellow_mask = cv2.inRange(hsv, YELLOW_LOWER, YELLOW_UPPER)
    white_mask  = cv2.inRange(hsv, WHITE_LOWER,  WHITE_UPPER)
    green_mask  = cv2.inRange(hsv, GREEN_LOWER,  GREEN_UPPER)
    return {
        "red":    cv2.countNonZero(red_mask),
        "yellow": cv2.countNonZero(yellow_mask),
        "white":  cv2.countNonZero(white_mask),
        "green":  cv2.countNonZero(green_mask),
    }

def analyze_frame(frame: np.ndarray) -> dict:
    h, w = frame.shape[:2]
    mid  = h // 2

    top_half    = frame[0:mid, 0:w]
    bottom_half = frame[mid:h, 0:w]

    top_counts    = detect_color_in_region(top_half)
    bottom_counts = detect_color_in_region(bottom_half)

    if top_counts["red"] > RED_THRESHOLD_TOP:
        top_result = "red"
    elif top_counts["green"] > GREEN_THRESHOLD:
        top_result = "green"
    else:
        top_result = "none"

    if bottom_counts["red"] > RED_THRESHOLD_BOTTOM:
        bottom_result = "red"
    elif bottom_counts["yellow"] > YELLOW_THRESHOLD:
        bottom_result = "yellow"
    elif bottom_counts["white"] > WHITE_THRESHOLD:
        bottom_result = "white"
    else:
        bottom_result = "none"

    return {
        "top":    top_result,
        "bottom": bottom_result,
        "raw":    {
            "top":    top_counts,
            "bottom": bottom_counts,
        }
    }

def get_camera_color(frame: np.ndarray = None) -> str:
    if frame is None:
        frame = get_frame()
    if frame is None:
        return "none"
    result = analyze_frame(frame)
    if result["top"] == "red" or result["bottom"] == "red":
        return "red"
    if result["bottom"] == "yellow":
        return "yellow"
    if result["top"] == "green":
        return "green"
    return "none"

def get_yellow_position(frame: np.ndarray = None) -> str:
    if frame is None:
        frame = get_frame()
    if frame is None:
        return "center"

    h, w        = frame.shape[:2]
    bottom_half = frame[h//2:h, 0:w]
    hsv         = cv2.cvtColor(bottom_half, cv2.COLOR_BGR2HSV)
    yellow_mask = cv2.inRange(hsv, YELLOW_LOWER, YELLOW_UPPER)

    left   = cv2.countNonZero(yellow_mask[:, 0:w//3])
    center = cv2.countNonZero(yellow_mask[:, w//3:2*w//3])
    right  = cv2.countNonZero(yellow_mask[:, 2*w//3:w])

    max_zone = max(left, center, right)
    if max_zone < YELLOW_ZONE_MIN:
        return "center"
    if left == max_zone:
        return "left"
    if right == max_zone:
        return "right"
    return "center"