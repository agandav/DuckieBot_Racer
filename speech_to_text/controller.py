# controller.py
import os
import subprocess
import sys

# ---------------------------------------------------------------------------
# Source /code/devel/setup.bash so duckietown_msgs is importable
# ---------------------------------------------------------------------------
def _source_ros_workspace():
    for setup_script in ["/code/devel/setup.bash", "/opt/ros/noetic/setup.bash"]:
        if not os.path.exists(setup_script):
            continue
        try:
            cmd = f"bash -c 'source {setup_script} && env'"
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            for line in proc.stdout.splitlines():
                if "=" in line:
                    key, _, val = line.partition("=")
                    os.environ[key] = val
        except Exception as e:
            print(f"[controller] Warning: could not source {setup_script}: {e}")

_source_ros_workspace()

from importlib import import_module

rospy = None
Twist2DStamped = None


def _load_ros():
    global rospy, Twist2DStamped
    if rospy is not None and Twist2DStamped is not None:
        return
    try:
        rospy = import_module("rospy")
        Twist2DStamped = import_module("duckietown_msgs.msg").Twist2DStamped
        print("[controller] ROS loaded successfully")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "ROS dependencies missing. Run inside the car-interface Docker container."
        ) from exc


ROBOT_NAME = "duckiebot18"

# Tune these on the physical robot
SPEEDS     = {"slow": 0.2, "normal": 0.35, "fast": 0.5}
TURN_OMEGA = 4.0    # radians/sec — tune this on the robot
TURN_DUR   = 0.5    # seconds per turn pulse — tune this on the robot

_pub = None


def init():
    global _pub
    _load_ros()
    rospy.init_node("voice_controller", anonymous=True)
    topic = f"/{ROBOT_NAME}/car_cmd_switch_node/cmd"
    _pub = rospy.Publisher(topic, Twist2DStamped, queue_size=1)
    rospy.sleep(0.5)
    print(f"[controller] Publishing to {topic}")


def _send(v: float, omega: float, duration: float = None):
    """
    Publish a wheel command.
    - duration=None  → publish and return immediately (continuous motion)
    - duration=float → publish, wait, then send stop (timed motion for turns)
    """
    msg = Twist2DStamped()
    msg.v = v
    msg.omega = omega
    _pub.publish(msg)

    if duration is not None:
        rospy.sleep(duration)
        msg.v = 0.0
        msg.omega = 0.0
        _pub.publish(msg)


def execute(command: dict):
    global _pub
    if _pub is None:
        init()

    action    = command.get("action")
    direction = command.get("direction")
    speed     = SPEEDS.get(command.get("speed") or "normal", 0.35)

    print(f"[controller] action={action} direction={direction} speed={speed}")

    if action == "stop":
        # explicit stop — send zero velocity
        _send(0.0, 0.0)

    elif action == "move" and direction == "forward":
        # no duration → keeps moving until next command
        _send(speed, 0.0)

    elif action == "move" and direction == "backward":
        # no duration → keeps moving until next command
        _send(-speed, 0.0)

    elif action == "turn" and direction == "left":
        # duration → stops after turn pulse
        _send(0.0, TURN_OMEGA, duration=TURN_DUR)

    elif action == "turn" and direction == "right":
        # duration → stops after turn pulse
        _send(0.0, -TURN_OMEGA, duration=TURN_DUR)

    elif action == "adjust":
        omega = TURN_OMEGA * 0.5 if direction == "left" else -TURN_OMEGA * 0.5
        _send(speed * 0.5, omega, duration=0.2)

    else:
        print(f"[controller] Unhandled: {command}")