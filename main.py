"""
main.py — DuckieBot Racer

Loop logic (every iteration):
    1. Sensor check first (ToF + camera) — highest priority
       - ToF < threshold OR cam = red  → stop
       - ToF > threshold AND cam != red AND was stopped → auto resume
       - cam = yellow → lane follow
    2. Voice command check
       - "stop" / "pause"           → stop
       - "forward"                  → move forward (default mode)
       - "turn left" / "turn right" → steer (works even when stopped)
       - "backwards"                → reverse
       - "faster" / "slower"        → adjust speed
       - "race complete"            → exit loop

Run:
    python main.py --dry-run
    python main.py --hostname duckiebot-01.local
"""

import argparse
import threading
import time

import speech_to_text.stt as stt
from interpreter import parse

# ---------------------------------------------------------------------------
# Shared state — written by STT thread, read by main loop
# ---------------------------------------------------------------------------
latest_command = None       # most recent parsed voice command dict
race_complete  = False      # set True to exit the loop
command_lock   = threading.Lock()

# ---------------------------------------------------------------------------
# Sensor stubs — replace with real sensor calls 
# ---------------------------------------------------------------------------
def get_tof_distance() -> float:
    """Returns distance in cm. Replace with real ToF sensor read."""
    print("[TOF]  Reading distance...")
    return 100.0    # stub: always clear

def get_camera_color() -> str:
    """Returns 'red', 'yellow', 'green', or 'none'. Replace with real camera read."""
    print("[CAM]  Reading camera...")
    return "green"  # stub: always green

# ---------------------------------------------------------------------------
# Robot action stubs — replace with real HTTP POST to duckiebot_receiver.py
# ---------------------------------------------------------------------------
def send_command(action: str, direction: str = None, speed: str = "normal"):
    print(f"[ROBOT] action={action}  direction={direction}  speed={speed}")
    # TODO: replace with real send_http_command(hostname, {...})

def robot_stop():
    print("[ROBOT] STOP")
    send_command("stop")

def robot_forward(speed="normal"):
    print(f"[ROBOT] FORWARD  speed={speed}")
    send_command("move", "forward", speed)

def robot_turn(direction: str):
    print(f"[ROBOT] TURN {direction.upper()}")
    send_command("turn", direction)
    time.sleep(1.0)     # wait for turn to complete before resuming loop

def robot_backward():
    print("[ROBOT] BACKWARD")
    send_command("move", "backward")

def robot_lane_follow():
    print("[ROBOT] LANE FOLLOW")
    send_command("lane_follow")

# ---------------------------------------------------------------------------
# STT callback — fires on every recognized phrase (runs in STT thread)
# ---------------------------------------------------------------------------
def on_speech(text: str):
    global latest_command, race_complete

    print(f"[STT]  '{text}'")

    # check for race complete first
    if any(p in text.lower() for p in ["race complete", "finish", "end race", "done"]):
        print("[STT]  Race complete signal received.")
        race_complete = True
        return

    # parse everything else through LLM
    try:
        command = parse(text)
        print(f"[LLM]  {command}")
        with command_lock:
            latest_command = command
    except Exception as e:
        print(f"[LLM]  Parse error: {e}")

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    global latest_command, race_complete

    parser = argparse.ArgumentParser(description="DuckieBot Racer")
    parser.add_argument("--hostname", default=None, help="Robot hostname or IP")
    parser.add_argument("--dry-run", action="store_true", help="Print commands, don't send")
    args = parser.parse_args()

    # --- Reset: everything reinitializes fresh on each run ---
    print("[INIT] Resetting — speed=0, wheels=forward")
    current_speed = "normal"
    is_stopped    = False   # True when stopped by sensor or voice
    is_moving     = False   # True once "forward" has been said

    TOF_THRESHOLD = 30.0    # cm — stop if closer than this

    # --- Start STT continuous recognition ---
    stt.start(on_recognized=on_speech)
    print("[INIT] Listening for commands. Say 'forward' to begin.")
    print("[INIT] Say 'race complete' to finish.")
    print("=" * 50)

    # --- Main loop ---
    while not race_complete:
        time.sleep(0.1)     # loop tick

        # ----------------------------------------------------------------
        # 1. SENSOR CHECKS (highest priority)
        # ----------------------------------------------------------------
        tof_dist  = get_tof_distance()
        cam_color = get_camera_color()

        sensor_blocked = (tof_dist < TOF_THRESHOLD) or (cam_color == "red")

        if sensor_blocked:
            if not is_stopped:
                print(f"[SENSOR] Blocked! tof={tof_dist:.1f}cm  cam={cam_color} — stopping.")
                robot_stop()
                is_stopped = True

        elif is_stopped:
            # path cleared on its own — auto resume if we were moving
            print("[SENSOR] Path clear — auto resuming.")
            is_stopped = False
            if is_moving:
                robot_forward(current_speed)

        # camera color actions (only when not blocked)
        if not sensor_blocked:
            if cam_color == "yellow":
                print("[CAM]  Yellow detected — lane following.")
                robot_lane_follow()
            # green = nothing, keep going

        # ----------------------------------------------------------------
        # 2. VOICE COMMAND CHECK
        # ----------------------------------------------------------------
        with command_lock:
            cmd = latest_command
            latest_command = None   # consume the command

        if cmd is None:
            continue    # no new voice command this tick

        action    = cmd.get("action")
        direction = cmd.get("direction")
        speed     = cmd.get("speed") or current_speed

        # stop
        if action == "stop":
            print("[CMD]  Voice stop.")
            robot_stop()
            is_stopped = True
            is_moving  = False

        # forward — starts robot, clears any voice-stop
        elif action == "move" and direction == "forward":
            print("[CMD]  Voice forward.")
            current_speed = speed
            is_moving  = True
            is_stopped = False
            robot_forward(current_speed)

        # turn — works even when stopped by sensor (steer around obstacle)
        elif action == "turn":
            print(f"[CMD]  Voice turn {direction}.")
            robot_turn(direction)
            # after steering, resume forward if we were moving
            if is_moving:
                is_stopped = False
                robot_forward(current_speed)

        # backward
        elif action == "move" and direction == "backward":
            print("[CMD]  Voice backward.")
            robot_backward()
            is_moving = False

        # speed adjust
        elif action == "adjust" or speed != current_speed:
            current_speed = speed
            print(f"[CMD]  Speed adjusted to {current_speed}.")
            if is_moving and not is_stopped:
                robot_forward(current_speed)

        else:
            print(f"[CMD]  Unhandled command: {cmd}")

    # ----------------------------------------------------------------
    # Race complete — clean up
    # ----------------------------------------------------------------
    print("=" * 50)
    print("[DONE] Race complete. Stopping robot.")
    robot_stop()
    stt.stop()
    print("[DONE] Goodbye.")


if __name__ == "__main__":
    main()