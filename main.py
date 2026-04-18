"""
main.py — DuckieBot Racer

Logic:
    - Each voice command executes ONCE — no resending, no defaults
    - Robot stops after every command and waits for next instruction
    - Sensors can override and stop the robot (ToF + red light)
    - Sensor clear → auto resume only if robot was moving

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
latest_command    = None
race_complete     = False
command_lock      = threading.Lock()
args              = None
_last_speech_time = 0.0    # STT cooldown tracker

# ---------------------------------------------------------------------------
# Fast keyword matching — no GPT needed for simple commands
# Order matters — longer phrases must come before shorter ones
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

STT_COOLDOWN = 0.8  # seconds between commands

def contains_command(text):
    return any(w in text.lower() for w in COMMAND_WORDS)

def parse_fast(text):
    text_lower = text.lower().strip().rstrip(".")
    for keyword, command in QUICK_COMMANDS:
        if keyword in text_lower:
            print("[FAST] Matched '{}' — skipping GPT".format(keyword))
            return command
    return None

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def _http_post(path, payload):
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        url="http://{}:8888{}".format(args.hostname, path),
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=2.0) as resp:
        return json.loads(resp.read().decode("utf-8"))

def _http_get(path):
    req = urllib.request.Request(
        url="http://{}:8888{}".format(args.hostname, path),
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=2.0) as resp:
        return json.loads(resp.read().decode("utf-8"))

def send_command(action, direction=None, speed="normal"):
    if args.dry_run or not args.hostname:
        print("[ROBOT] action={}  direction={}  speed={}".format(action, direction, speed))
        return
    try:
        result = _http_post("/voice-command", {
            "action":    action,
            "direction": direction,
            "speed":     speed,
        })
        print("[HTTP] action={} ok={}".format(action, result.get("ok")))
    except urllib.error.URLError as e:
        print("[ERR]  Could not reach robot: {}".format(e))
    except Exception as e:
        print("[ERR]  send_command failed: {}".format(e))

def get_camera_reading():
    if args.dry_run or not args.hostname:
        return "none", "center"
    try:
        result = _http_get("/camera-color")
        return result.get("color", "none"), result.get("position", "center")
    except Exception:
        return "none", "center"  # fail silently

# ---------------------------------------------------------------------------
# Robot actions — each executes once then stops (duration handled by controller)
# ---------------------------------------------------------------------------
def robot_stop():
    print("[ROBOT] STOP")
    send_command("stop")

def robot_forward(speed="normal"):
    print("[ROBOT] FORWARD  speed={}".format(speed))
    send_command("move", "forward", speed)

def robot_turn(direction):
    print("[ROBOT] TURN {}".format(direction.upper()))
    send_command("turn", direction)
    time.sleep(1.0)
    # flush any commands that queued during the turn
    with command_lock:
        global latest_command
        latest_command = None
    print("[TURN] Done")

def robot_backward(speed="normal"):
    print("[ROBOT] BACKWARD  speed={}".format(speed))
    send_command("move", "backward", speed)

def robot_lane_follow(yellow_pos):
    print("[ROBOT] LANE FOLLOW  yellow={}".format(yellow_pos))
    if yellow_pos == "left":
        send_command("adjust", "left")
    elif yellow_pos == "right":
        send_command("adjust", "right")
    else:
        send_command("move", "forward")

# ---------------------------------------------------------------------------
# ToF stub — replace with real sensor read
# ---------------------------------------------------------------------------
def get_tof_distance():
    return 100.0    # stub: always clear

# ---------------------------------------------------------------------------
# STT callback — runs in STT thread
# ---------------------------------------------------------------------------
def on_speech(text):
    global latest_command, race_complete, _last_speech_time

    now = time.time()

    if not text or not text.strip():
        return

    print("[STT]  '{}'".format(text))

    # filter background noise
    if not contains_command(text):
        print("[STT]  Ignored (no command word found)")
        return

    # cooldown
    if now - _last_speech_time < STT_COOLDOWN:
        print("[STT]  Ignored (cooldown {:.2f}s remaining)".format(
            STT_COOLDOWN - (now - _last_speech_time)
        ))
        return

    _last_speech_time = now

    # race complete — highest priority
    if any(p in text.lower() for p in ["race complete", "finish", "end race", "done"]):
        print("[STT]  Race complete signal received.")
        race_complete = True
        return

    # fast keyword match first
    command = parse_fast(text)

    # fall back to GPT only if no keyword matched
    if command is None:
        print("[LLM]  No keyword match — calling GPT...")
        try:
            command = parse(text)
            print("[LLM]  {}".format(command))
        except Exception as e:
            print("[LLM]  Parse error: {}".format(e))
            return

    with command_lock:
        latest_command = command

# ---------------------------------------------------------------------------
# Camera thread
# ---------------------------------------------------------------------------
camera_data = {"color": "none", "position": "center"}
camera_lock = threading.Lock()

def camera_thread_fn():
    while not race_complete:
        try:
            color, position = get_camera_reading()
            with camera_lock:
                camera_data["color"]    = color
                camera_data["position"] = position
        except Exception:
            pass
        time.sleep(0.1)

def stt_thread_fn():
    stt.start(on_recognized=on_speech)
    print("[STT] Speech-to-text thread started.")

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
        print("[INIT] Connecting to robot at {}".format(args.hostname))

    current_speed = "normal"
    is_stopped    = False   # True when stopped by sensor
    is_moving     = False   # True when last command was forward
    is_reversing  = False   # True when last command was backward

    TOF_THRESHOLD = 30.0    # cm

    # start background threads
    threading.Thread(target=camera_thread_fn, daemon=True).start()
    threading.Thread(target=stt_thread_fn,    daemon=True).start()

    print("[INIT] Listening for commands. Say 'forward' to begin.")
    print("[INIT] Say 'race complete' to finish.")
    print("=" * 50)

    while not race_complete:
        time.sleep(0.1)

        # ----------------------------------------------------------------
        # 1. SENSOR CHECKS
        # ----------------------------------------------------------------
        tof_dist = get_tof_distance()
        with camera_lock:
            cam_color  = camera_data["color"]
            yellow_pos = camera_data["position"]

        sensor_blocked = (tof_dist < TOF_THRESHOLD) or (cam_color == "red")

        if sensor_blocked:
            if not is_stopped:
                print("[SENSOR] Blocked! tof={:.1f}cm  cam={} — stopping.".format(
                    tof_dist, cam_color))
                robot_stop()
                is_stopped = True

        elif is_stopped:
            # auto resume only if sensor caused the stop
            if is_moving or is_reversing:
                print("[SENSOR] Path clear — auto resuming.")
                is_stopped = False
                if is_moving:
                    robot_forward(current_speed)
                elif is_reversing:
                    robot_backward(current_speed)
            else:
                is_stopped = False  # voice stop — don't auto resume

        # lane follow when yellow detected and not blocked
        if not sensor_blocked and not is_stopped:
            if cam_color == "yellow":
                print("[CAM]  Yellow — lane following ({}).".format(yellow_pos))
                robot_lane_follow(yellow_pos)

        # ----------------------------------------------------------------
        # 2. VOICE COMMAND CHECK — execute once, no resend
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

        elif action == "turn":
            print("[CMD]  Voice turn {}.".format(direction))
            robot_turn(direction)
            # no auto-resume — robot stops after turn, waits for next command

        elif action == "move" and direction == "backward":
            print("[CMD]  Voice backward.")
            current_speed = speed
            is_reversing  = True
            is_moving     = False
            is_stopped    = False
            robot_backward(current_speed)

        elif action == "adjust":
            current_speed = speed
            print("[CMD]  Speed adjusted to {}.".format(current_speed))

        else:
            print("[CMD]  Unhandled command: {}".format(cmd))

    # ----------------------------------------------------------------
    # Race complete
    # ----------------------------------------------------------------
    print("=" * 50)
    print("[DONE] Race complete. Stopping robot.")
    robot_stop()
    stt.stop()
    print("[DONE] Goodbye.")


if __name__ == "__main__":
    main()