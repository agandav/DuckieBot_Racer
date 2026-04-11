#!/usr/bin/env python3

import rospy
from sensor_msgs.msg import Range

from dt_robot_utils import get_robot_name

SENSOR_NAME: str = "front_center"

# This node listens to the ToF sensor topic and prints the distance to the console. if too far it will print "Too-far". This is useful for testing the ToF sensor and making sure it's working correctly. It can also be used as a starting point for more complex applications that use the ToF sensor data.
def callback(msg: Range):
    distance: str = f"{msg.range:.3f}m" if msg.range < msg.max_range else "Too-far"
    print(f"Range: {distance}")
    return distance

#continuously runs the node to listen ot the tof sensor
def listener():
    robot_name: str = get_robot_name()
    # initialize node
    rospy.init_node('listener', anonymous=True)
    # setup tof listener
    rospy.Subscriber(
        f"/{robot_name}/{SENSOR_NAME}_tof_driver_node/range",
        Range,
        callback,
    )
    # keep the node alive
    rospy.spin()

if __name__ == '__main__':
    listener()
