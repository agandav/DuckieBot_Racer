import os
import subprocess
import sys

# ---------------------------------------------------------------------------
# Source ROS workspace so duckietown_msgs is importable
# ---------------------------------------------------------------------------
def _source_ros_workspace():
    for setup_script in ["/code/devel/setup.bash", "/opt/ros/noetic/setup.bash"]:
        if not os.path.exists(setup_script):
            continue
        try:
            cmd = "bash -c 'source {} && env'".format(setup_script)
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            for line in proc.stdout.splitlines():
                if "=" in line:
                    key, _, val = line.partition("=")
                    os.environ[key] = val
        except Exception as e:
            print("[controller] Warning: could not source {}: {}".format(setup_script, e))

_source_ros_workspace()

from importlib import import_module

rospy          = None
Twist2DStamped = None


def _load_ros():
    global rospy, Twist2DStamped
    if rospy is not None and Twist2DStamped is not None:
        return
    try:
        rospy          = import_module("rospy")
        Twist2DStamped = import_module("duckietown_msgs.msg").Twist2DStamped
        print("[controller] ROS loaded successfully")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "ROS dependencies missing. Run inside the car-interface Docker container."
        ) from exc


ROBOT_NAME = "duckiebot18"
SPEEDS     = {"slow": 0.2, "normal": 0.35, "fast": 0.5}
TURN_OMEGA = 4.0    # radians/sec — tune on robot
TURN_DUR   = 0.5    # seconds per turn pulse — tune on robot

_pub = None


def init():
    global _pub
    _load_ros()
    # camera.py may have already called init_node — handle gracefully
    try:
        rospy.init_node("voice_controller", anonymous=True)
    except rospy.exceptions.ROSException:
        pass  # node already initialized, that's fine
    topic = "/{}/car_cmd_switch_node/cmd".format(ROBOT_NAME)
    _pub = rospy.Publisher(topic, Twist2DStamped, queue_size=1)
    rospy.sleep(0.5)
    print("[controller] Publishing to {}".format(topic))


def _send(v, omega, duration=None):
    """
    Publish a wheel command.
    duration=None  → publish and return (continuous motion)
    duration=float → publish, wait, then stop (timed motion for turns)
    """
    msg     = Twist2DStamped()
    msg.v   = v
    msg.omega = omega
    _pub.publish(msg)

    if duration is not None:
        rospy.sleep(duration)
        msg.v     = 0.0
        msg.omega = 0.0
        _pub.publish(msg)


def execute(command):
    global _pub
    if _pub is None:
        init()

    action    = command.get("action")
    direction = command.get("direction")
    speed     = SPEEDS.get(command.get("speed") or "normal", 0.35)

    print("[controller] action={} direction={} speed={}".format(action, direction, speed))

    if action == "stop":
        _send(0.0, 0.0)

    elif action == "move" and direction == "forward":
        _send(speed, 0.0)

    elif action == "move" and direction == "backward":
        _send(-speed, 0.0)

    elif action == "turn" and direction == "left":
        _send(0.0, TURN_OMEGA, duration=TURN_DUR)

    elif action == "turn" and direction == "right":
        _send(0.0, -TURN_OMEGA, duration=TURN_DUR)

    elif action == "adjust":
        omega = TURN_OMEGA * 0.5 if direction == "left" else -TURN_OMEGA * 0.5
        _send(speed * 0.5, omega, duration=0.2)

    else:
        print("[controller] Unhandled: {}".format(command))