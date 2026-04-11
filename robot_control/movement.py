import time

current_speed = 0.3


def move_forward(duration: float = 1.0):
    print(f"Moving forward at speed {current_speed} for {duration}s")
    # TODO: replace with ROS wheel command
    # send_wheel_cmd(current_speed, current_speed)
    time.sleep(duration)
    stop()


def turn_left(degrees: float = 90):
    duration = degrees / 90.0 * 1.2  # ~1.2 sec per 90 degrees — calibrate on robot
    print(f"Turning left {degrees}° ({duration:.1f}s) at speed {current_speed}")
    # TODO: replace with ROS wheel command
    # send_wheel_cmd(-current_speed, current_speed)
    time.sleep(duration)
    stop()


def turn_right(degrees: float = 90):
    duration = degrees / 90.0 * 1.2  # ~1.2 sec per 90 degrees — calibrate on robot
    print(f"Turning right {degrees}° ({duration:.1f}s) at speed {current_speed}")
    # TODO: replace with ROS wheel command
    # send_wheel_cmd(current_speed, -current_speed)
    time.sleep(duration)
    stop()


def stop():
    print("Stopping")
    # TODO: replace with ROS wheel command
    # send_wheel_cmd(0.0, 0.0)


def increase_speed():
    global current_speed
    current_speed = min(current_speed + 0.1, 1.0)
    print(f"Increased speed to {current_speed:.1f}")


def decrease_speed():
    global current_speed
    current_speed = max(current_speed - 0.1, 0.0)
    print(f"Decreased speed to {current_speed:.1f}")


def lane_follow():
    print("Lane following mode activated")
    # TODO: implement camera-based lane following


# ---------------------------------------------------------------------------
# ROS integration — uncomment and fill in once robot is running
# ---------------------------------------------------------------------------
# import rospy
# from duckietown_msgs.msg import WheelsCmdStamped
#
# rospy.init_node('voice_driver', anonymous=True)
# _pub = rospy.Publisher(
#     '/duckie/wheels_driver_node/wheels_cmd',
#     WheelsCmdStamped,
#     queue_size=1
# )
#
# def send_wheel_cmd(left: float, right: float):
#     msg = WheelsCmdStamped()
#     msg.vel_left = left
#     msg.vel_right = right
#     _pub.publish(msg)