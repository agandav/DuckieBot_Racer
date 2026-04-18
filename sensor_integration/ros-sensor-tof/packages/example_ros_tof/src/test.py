import time

THRESHOLD_MM = 200  # stop if object closer than 20 cm

def monitor_tof(sensor, stop_callback):
    """
    Continuously read ToF sensor and trigger stop_callback
    when distance goes below threshold.
    """
    while True:
        try:
            distance = sensor.get_distance()  # in mm (depends on your lib)
            print(f"Distance: {distance} mm")

            if distance is not None and distance < THRESHOLD_MM:
                print("Obstacle detected! Stopping robot.")
                stop_callback()
                break  # remove this if you want it to keep checking after stop

            time.sleep(0.05)  # ~20 Hz
        except Exception as e:
            print(f"Sensor error: {e}")
            time.sleep(0.1)