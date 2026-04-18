"""
main.py — DuckieBot Racer

Loop logic (every iteration):
    1. GET /camera-color from robot — gets color + yellow position in one call
    2. Sensor check (ToF + camera) — highest priority
       - ToF < threshold OR cam = red  → stop
       - cam = yellow → lane follow using yellow position
       - auto resume when path clears (only if sensor caused stop)
    3. Continuous motion — re-send forward/backward every 0.5s
    4. Voice command check

Run:
    python main.py --dry-run
    python main.py --hostname duckiebot18.local
"""

import argparse
import json
import threading
import time
import urllib.error
import urllib.request

import speech_to_text.stt as stt
from interpreter import parse

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------
latest_command = None
race_complete  = False
command_lock   = threading.Lock()
args           = None

# ---------------------------------------------------------------------------
# Fast keyword matching — no GPT needed for simple commands
# ---------------------------------------------------------------------------
QUICK_COMMANDS = [
    ("turn left",   {"action": "turn",   "direction": "left",     "speed": None}),
    ("turn right",  {"action": "turn",   "direction": "right",    "speed": None}),
    ("go left",     {"action": "turn",   "direction": "left",     "speed": None}),
    ("go right",    {"action": "turn",   "direction": "right",    "speed": None}),
    ("speed up",    {"action": "adjust", "direction": None,       "speed": "fast"}),
    ("slow down",   {"action": "adjust", "direction": None,       "speed": "slow"}),
    ("go forward",  {"action": "move",   "direction": "forward",  "speed": "normal"}),
    ("go back",     {"action": "move",   "direction": "backward", "speed": "normal"}),
    ("forward",     {"action": "move",   "direction": "forward",  "speed": "normal"}),
    ("go",          {"action": "move",   "direction": "forward",  "speed": "normal"}),
    ("ahead",       {"action": "move",   "direction": "forward",  "speed": "normal"}),
    ("straight",    {"action": "move",   "direction": "forward",  "speed": "normal"}),
    ("move",        {"action": "move",   "direction": "forward",  "speed": "normal"}),
    ("backward",    {"action": "move",   "direction": "backward", "speed": "normal"}),
    ("reverse",     {"action": "move",   "direction": "backward", "speed": "normal"}),
    ("back",        {"action": "move",   "direction": "backward", "speed": "normal"}),
    ("left",        {"action": "turn",   "direction": "left",     "speed": None}),
    ("right",       {"action": "turn",   "direction": "right",    "speed": None}),
    ("stop",        {"action": "stop",   "direction": None,       "speed": None}),
    ("halt",        {"action": "stop",   "direction": None,       "speed": None}),
    ("brake",       {"action": "stop",   "direction": None,       "speed": None}),
    ("pause",       {"action": "stop",   "direction": None,       "speed": None}),
    ("freeze",      {"action": "stop",   "direction": None,       "speed": None}),
    ("faster",      {"action": "adjust", "direction": None,       "speed": "fast"}),
    ("slower",      {"action": "adjust", "direction": None,       "speed": "slow"}),
]

COMMAND_WORDS = [w for w, _ in QUICK_COMMANDS] + ["race complete", "finish", "end race", "done"]

def contains_command(text: str) -> bool:
    text_lower = text.lower()
    return any(w in text_lower for w in COMMAND_WORDS)

def parse_fast(text: str) -> dict | None:
    text_lower = text.lower().strip().rstrip(".")
    for keyword, command in QUICK_COMMANDS:
        if keyword in text_lower:
            print(f"[FAST] Matched '{keyword}' — skipping GPT")
            return command
    return None

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def _http_post(path: str, payload: dict):
    """POST JSON to robot."""
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        url=f"http://{args.hostname}:8888{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=2.0) as resp:
        return json.loads(resp.read().decode("utf-8"))

def _http_get(path: str) -> dict:
    """GET from robot, returns parsed JSON."""
    req = urllib.request.Request(
        url=f"http://{args.hostname}:8888{path}",
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=2.0) as resp:
        return json.loads(resp.read().decode("utf-8"))

def send_command(action: str, direction: str = None, speed: str = "normal"):
    if args.dry_run or not args.hostname:
        print(f"[ROBOT] action={action}  direction={direction}  speed={speed}")
        return
    try:
        result = _http_post("/voice-command", {
            "action":    action,
            "direction": direction,
            "speed":     speed,
        })
        print(f"[HTTP] action={action} ok={result.get('ok')}")
    except urllib.error.URLError as e:
        print(f"[ERR]  Could not reach robot: {e}")
    except Exception as e:
        print(f"[ERR]  send_command failed: {e}")

def get_camera_reading() -> tuple[str, str]:
    """
    GET /camera-color from robot.
    Returns (color, yellow_position).
    color:    "red" | "yellow" | "green" | "none"
    position: "left" | "right" | "center"
    """
    if args.dry_run or not args.hostname:
        return "none", "center"
    try:
        result = _http_get("/camera-color")
        return result.get("color", "none"), result.get("position", "center")
    except Exception as e:
        print(f"[ERR]  Camera read failed: {e}")
        return "none", "center"

# ---------------------------------------------------------------------------
# Robot actions
# ---------------------------------------------------------------------------
def robot_stop():
    print("[ROBOT] STOP")
    send_command("stop")

def robot_forward(speed="normal"):
    print(f"[ROBOT] FORWARD  speed={speed}")
    send_command("move", "forward", speed)

def robot_turn(direction: str):
    print(f"[ROBOT] TURN {direction.upper()}")
    send_command("turn", direction)
    time.sleep(1.0)

def robot_backward(speed="normal"):
    print(f"[ROBOT] BACKWARD  speed={speed}")
    send_command("move", "backward", speed)

def robot_lane_follow(yellow_pos: str):
    print(f"[ROBOT] LANE FOLLOW  yellow={yellow_pos}")
    if yellow_pos == "left":
        send_command("adjust", "left")
    elif yellow_pos == "right":
        send_command("adjust", "right")
    else:
        send_command("move", "forward")

# ---------------------------------------------------------------------------
# ToF stub — replace with real sensor
# ---------------------------------------------------------------------------
def get_tof_distance() -> float:
    return 100.0

# ---------------------------------------------------------------------------
# STT callback
# ---------------------------------------------------------------------------
def on_speech(text: str):
    global latest_command, race_complete

    if not text or not text.strip():
        return

    print(f"[STT]  '{text}'")

    if not contains_command(text):
        print(f"[STT]  Ignored (no command word found)")
        return

    if any(p in text.lower() for p in ["race complete", "finish", "end race", "done"]):
        race_complete = True
        return

    command = parse_fast(text)
    if command is None:
        print("[LLM]  No keyword match — calling GPT...")
        try:
            command = parse(text)
            print(f"[LLM]  {command}")
        except Exception as e:
            print(f"[LLM]  Parse error: {e}")
            return

    with command_lock:
        latest_command = command

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    global latest_command, race_complete, args

    parser = argparse.ArgumentParser(description="DuckieBot Racer")
    parser.add_argument("--hostname", default="duckiebot18.local")
    parser.add_argument("--dry-run",  action="store_true")
    args = parser.parse_args()

    print("[INIT] Resetting — speed=0, wheels=forward")
    if args.dry_run:
        print("[INIT] DRY RUN mode")
    else:
        print(f"[INIT] Connecting to robot at {args.hostname}")

    current_speed      = "normal"
    is_stopped         = False
    is_moving          = False
    is_reversing       = False
    last_forward_time  = 0.0
    last_backward_time = 0.0
    RESEND_INTERVAL    = 0.5
    TOF_THRESHOLD      = 30.0

    stt.start(on_recognized=on_speech)
    print("[INIT] Listening for commands. Say 'forward' to begin.")
    print("[INIT] Say 'race complete' to finish.")
    print("=" * 50)

    while not race_complete:
        time.sleep(0.1)
        now = time.time()

        # ----------------------------------------------------------------
        # 1. SENSOR CHECKS
        #    One HTTP call gets both color AND yellow position from robot
        # ----------------------------------------------------------------
        tof_dist             = get_tof_distance()
        cam_color, yellow_pos = get_camera_reading()

        sensor_blocked = (tof_dist < TOF_THRESHOLD) or (cam_color == "red")

        if sensor_blocked:
            if not is_stopped:
                print(f"[SENSOR] Blocked! tof={tof_dist:.1f}cm  cam={cam_color} — stopping.")
                robot_stop()
                is_stopped = True

        elif is_stopped:
            if is_moving or is_reversing:
                print("[SENSOR] Path clear — auto resuming.")
                is_stopped = False
                if is_moving:
                    robot_forward(current_speed)
                    last_forward_time = now
                elif is_reversing:
                    robot_backward(current_speed)
                    last_backward_time = now
            else:
                is_stopped = False  # voice stop — don't auto resume

        # ----------------------------------------------------------------
        # 2. CONTINUOUS MOTION
        # ----------------------------------------------------------------
        if not sensor_blocked and not is_stopped:
            if cam_color == "yellow":
                print(f"[CAM]  Yellow — lane following ({yellow_pos}).")
                robot_lane_follow(yellow_pos)
                last_forward_time = now

            elif is_moving:
                if now - last_forward_time >= RESEND_INTERVAL:
                    robot_forward(current_speed)
                    last_forward_time = now

            elif is_reversing:
                if now - last_backward_time >= RESEND_INTERVAL:
                    robot_backward(current_speed)
                    last_backward_time = now

        # ----------------------------------------------------------------
        # 3. VOICE COMMAND CHECK
        # ----------------------------------------------------------------
        with command_lock:
            cmd = latest_command
            latest_command = None

        if cmd is None:
            continue

        action    = cmd.get("action")
        direction = cmd.get("direction")
        speed     = cmd.get("speed") or current_speed

        if action == "stop":
            print("[CMD]  Voice stop.")
            robot_stop()
            is_stopped   = True
            is_moving    = False
            is_reversing = False

        elif action == "move" and direction == "forward":
            print("[CMD]  Voice forward.")
            current_speed = speed
            is_moving     = True
            is_reversing  = False
            is_stopped    = False
            robot_forward(current_speed)
            last_forward_time = now

        elif action == "turn":
            print(f"[CMD]  Voice turn {direction}.")
            robot_turn(direction)
            if is_moving:
                is_stopped = False
                robot_forward(current_speed)
                last_forward_time = now

        elif action == "move" and direction == "backward":
            print("[CMD]  Voice backward.")
            current_speed  = speed
            is_reversing   = True
            is_moving      = False
            is_stopped     = False
            robot_backward(current_speed)
            last_backward_time = now

        elif action == "adjust" or speed != current_speed:
            current_speed = speed
            print(f"[CMD]  Speed adjusted to {current_speed}.")
            if is_moving and not is_stopped:
                robot_forward(current_speed)
                last_forward_time = now
            elif is_reversing and not is_stopped:
                robot_backward(current_speed)
                last_backward_time = now

        else:
            print(f"[CMD]  Unhandled command: {cmd}")

    print("=" * 50)
    print("[DONE] Race complete. Stopping robot.")
    robot_stop()
    stt.stop()
    print("[DONE] Goodbye.")


if __name__ == "__main__":
    main()