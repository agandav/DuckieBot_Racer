from robot_control.movement import (
    move_forward,
    turn_left,
    turn_right,
    stop,
    increase_speed,
    decrease_speed,
    lane_follow,
)


def execute_command(action: str, value: float = 1.0):
    """
    Execute a single command.
    - action: one of "forward", "backward", "left", "right",
                     "stop", "faster", "slower", "lane_follow"
    - value:  duration in seconds (forward/backward) OR degrees (left/right)
    """
    if action == "forward":
        move_forward(value)
    elif action == "backward":
        move_forward(-value)  # movement.py will handle negative as backward
    elif action == "left":
        turn_left(value)
    elif action == "right":
        turn_right(value)
    elif action == "stop":
        stop()
    elif action == "faster":
        increase_speed()
    elif action == "slower":
        decrease_speed()
    elif action == "lane_follow":
        lane_follow()
    else:
        print(f"Unknown command: {action}")


def execute_commands(command_list: list[dict]):
    """
    Entry point for LLM output.

    Expected format:
        [
            {"action": "forward", "value": 2.0},
            {"action": "right",   "value": 90},
            {"action": "stop",    "value": 0},
        ]
    """
    for cmd in command_list:
        action = cmd.get("action", "")
        value = cmd.get("value", 1.0)
        execute_command(action, value)