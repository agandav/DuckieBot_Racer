#!/usr/bin/env python3
"""
camera.py — Split-frame color detection for DuckieBot racer

Frame is divided into two halves:
    TOP HALF    → traffic lights, stop signs (far/high objects)
    BOTTOM HALF → ground tape detection (yellow lane line, white edge, red stop line)

Returns a dict:
    {
        "top":    "red" | "green" | "none",
        "bottom": "red" | "yellow" | "white" | "none"
    }

Main logic in main.py reads this and decides:
    - top == "red"    → stop (traffic light or stop sign)
    - top == "green"  → go (traffic light)
    - bottom == "red" → stop (stop line tape)
    - bottom == "yellow" → lane follow (center line)
    - bottom == "white"  → lane edge warning (drifting out)
"""

import cv2
import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# HSV color ranges
# HSV = Hue, Saturation, Value
#   Hue:        0-180 in OpenCV (color wheel, red=0/180, yellow=30, green=60, white=any)
#   Saturation: 0-255 (0=gray/white, 255=vivid color)
#   Value:      0-255 (0=black, 255=bright)
#
# Red wraps around the hue wheel so we need TWO ranges:
#   lower red: hue 0-10
#   upper red: hue 170-180
# Yellow is a narrow band around hue 20-35
# White has low saturation and high value (it's nearly colorless but bright)
# Green is hue 40-80
# ─────────────────────────────────────────────────────────────────────────────

# Red (two ranges because red wraps around hue=0/180)
RED_LOWER_1 = np.array([0,   120, 70])
RED_UPPER_1 = np.array([10,  255, 255])
RED_LOWER_2 = np.array([170, 120, 70])
RED_UPPER_2 = np.array([180, 255, 255])

# Yellow tape (center lane line)
YELLOW_LOWER = np.array([18, 80, 80])
YELLOW_UPPER = np.array([35, 255, 255])

# White tape (lane edge)
WHITE_LOWER = np.array([0,  0,   180])
WHITE_UPPER = np.array([180, 40, 255])

# Green traffic light
GREEN_LOWER = np.array([40, 80, 80])
GREEN_UPPER = np.array([80, 255, 255])

# ─────────────────────────────────────────────────────────────────────────────
# Pixel thresholds — how many pixels of a color need to be detected
# before we report it. Tune these on the actual robot.
# Higher = less sensitive (fewer false positives)
# Lower  = more sensitive (more false positives)
# ─────────────────────────────────────────────────────────────────────────────
RED_THRESHOLD_TOP    = 300   # traffic light/sign — smaller target, fewer pixels needed
RED_THRESHOLD_BOTTOM = 500   # stop line tape — bigger target
YELLOW_THRESHOLD     = 800   # yellow lane line — large area
WHITE_THRESHOLD      = 1000  # white edge tape — large area
GREEN_THRESHOLD      = 300   # traffic light green


def detect_color_in_region(region: np.ndarray) -> dict:
    """
    Takes a BGR image region (numpy array), converts to HSV,
    and checks for each color using masks.

    A mask is a black-and-white image where white pixels = "this color is here".
    cv2.countNonZero() counts the white pixels — more white = more of that color.

    Returns a dict of pixel counts for each color.
    """
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

    # Red needs two masks merged with bitwise OR (|) because it wraps around hue wheel
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
    """
    Splits the frame into top and bottom halves,
    runs color detection on each half separately.

    TOP HALF    → looking for traffic lights / stop signs (far, high up)
    BOTTOM HALF → looking for tape on the ground (close, low)

    Returns:
        {
            "top":    "red" | "green" | "none",
            "bottom": "red" | "yellow" | "white" | "none",
            "raw":    { top pixel counts, bottom pixel counts }  # for debugging
        }
    """
    h, w = frame.shape[:2]
    mid  = h // 2  # halfway point vertically

    top_half    = frame[0:mid, 0:w]    # rows 0 to mid
    bottom_half = frame[mid:h, 0:w]    # rows mid to bottom

    top_counts    = detect_color_in_region(top_half)
    bottom_counts = detect_color_in_region(bottom_half)

    # ── TOP HALF decision ──────────────────────────────────────────────────
    # Priority: red > green > none
    # Red traffic light or stop sign = stop immediately
    if top_counts["red"] > RED_THRESHOLD_TOP:
        top_result = "red"
    elif top_counts["green"] > GREEN_THRESHOLD:
        top_result = "green"
    else:
        top_result = "none"

    # ── BOTTOM HALF decision ───────────────────────────────────────────────
    # Priority: red > yellow > white > none
    # Red stop line on ground = stop
    # Yellow center line = lane follow
    # White edge = drifting out warning
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


def get_camera_color() -> str:
    """
    Simple interface for main.py — returns a single string.

    Maps the split-frame result to what main.py expects:
        "red"    → stop
        "yellow" → lane follow
        "green"  → go
        "none"   → nothing detected

    Priority: any red anywhere > bottom yellow > top green > none
    """
    cap = cv2.VideoCapture(0)  # 0 = laptop webcam for testing
                               # swap for robot camera stream when robot is on
    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("[CAM] Failed to read frame")
        return "none"

    result = analyze_frame(frame)

    # Red anywhere = stop (highest priority)
    if result["top"] == "red" or result["bottom"] == "red":
        return "red"

    # Yellow on ground = lane follow
    if result["bottom"] == "yellow":
        return "yellow"

    # Green light = go
    if result["top"] == "green":
        return "green"

    return "none"


# ─────────────────────────────────────────────────────────────────────────────
# Test mode — run this file directly to see live detection
# python sensor_integration/camera.py
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Camera test mode. Press Q to quit.")
    print("Hold colored objects in front of your webcam to test detection.")
    print()

    cap = cv2.VideoCapture(0)

    while True:
        ret, frame = cap.read()
        if not ret:
            print("No frame — check your webcam.")
            break

        h, w   = frame.shape[:2]
        mid    = h // 2
        result = analyze_frame(frame)

        # Draw dividing line between top and bottom halves
        cv2.line(frame, (0, mid), (w, mid), (255, 255, 255), 2)

        # Label each half
        cv2.putText(frame, f"TOP:    {result['top']}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)
        cv2.putText(frame, f"BOTTOM: {result['bottom']}",
                    (10, mid + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)

        # Show raw pixel counts for tuning thresholds
        raw_t = result["raw"]["top"]
        raw_b = result["raw"]["bottom"]
        cv2.putText(frame, f"red={raw_t['red']} grn={raw_t['green']}",
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)
        cv2.putText(frame, f"red={raw_b['red']} yel={raw_b['yellow']} wht={raw_b['white']}",
                    (10, mid + 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)

        # Overall decision
        overall = get_camera_color.__wrapped__(result) if hasattr(get_camera_color, '__wrapped__') else None
        cv2.putText(frame, f"DECISION: {result['top']} / {result['bottom']}",
                    (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)

        cv2.imshow("DuckieBot Camera Test", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()