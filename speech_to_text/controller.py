# controller.py
" Voice control for Duckiebot using speech-to-text and OpenAI for command parsing. "
"It listens for recognized speech, converts it to structured commands, and sends them to the robot via ROS topics."
" Note: This is a simplified example for demonstration purposes. In a production system, you would want to add error handling, support for more complex commands, and possibly a more robust communication mechanism with the robot. "
" Make sure to install the required dependencies and set up your ROS environment correctly before running this code. "

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
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "ROS dependencies are missing. Run this module from a ROS environment with rospy and duckietown_msgs installed."
        ) from exc

ROBOT_NAME = "YOUR_HOSTNAME"  # e.g. "csc22905"

# Tune these on the physical robot — these are starting guesses
SPEEDS = {"slow": 0.2, "normal": 0.35, "fast": 0.5}
TURN_OMEGA = 4.0  # radians/sec, tune this

_pub = None

def init():
    global _pub
    _load_ros()
    rospy.init_node("voice_controller", anonymous=True)
    topic = f"/{ROBOT_NAME}/car_cmd_switch_node/cmd"
    _pub = rospy.Publisher(topic, Twist2DStamped, queue_size=1)

def _send(v: float, omega: float, duration: float = 0.5):
    msg = Twist2DStamped()
    msg.v = v
    msg.omega = omega
    _pub.publish(msg)
    rospy.sleep(duration)
    # always send a stop after timed moves
    msg.v = 0.0
    msg.omega = 0.0
    _pub.publish(msg)

def execute(command: dict):
    if _pub is None:
        init()
    action = command.get("action")
    direction = command.get("direction")
    speed = SPEEDS.get(command.get("speed") or "normal", 0.35)

    if action == "stop":
        _send(0.0, 0.0, duration=0.0)
    elif action == "move" and direction == "forward":
        _send(speed, 0.0)
    elif action == "move" and direction == "backward":
        _send(-speed, 0.0)
    elif action == "turn" and direction == "left":
        _send(0.0, TURN_OMEGA)
    elif action == "turn" and direction == "right":
        _send(0.0, -TURN_OMEGA)
    elif action == "adjust":
        # small correction, shorter duration
        omega = TURN_OMEGA * 0.5 if direction == "left" else -TURN_OMEGA * 0.5
        _send(speed * 0.5, omega, duration=0.2)
    else:
        print(f"[controller] Unhandled: {command}")