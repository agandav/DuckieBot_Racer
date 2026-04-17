import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
import subprocess


class SimpleMotorDriver:
    def __init__(self, robot_name="duckiebot18", verbose=True):
        self.robot_name = robot_name
        self.verbose = verbose

    def set_wheels(self, left: float, right: float):
        if self.verbose:
            print(f"[MOTOR] left={left:.2f} right={right:.2f}")
        import subprocess
        subprocess.Popen([
            "rostopic", "pub", "-1",
            f"/{self.robot_name}/wheels_driver_node/wheels_cmd",
            "duckietown_msgs/WheelsCmdStamped",
            f"{{vel_left: {left}, vel_right: {right}}}"
        ])

    def stop(self):
        self.set_wheels(0.0, 0.0)

class ActionExecutor:
    def __init__(self, driver, forward_speed=0.35, turn_speed=0.28, turn_bias=0.55, pulse_sec=0.35):
        self.driver = driver
        self.forward_speed = forward_speed
        self.turn_speed = turn_speed
        self.turn_bias = turn_bias
        self.pulse_sec = pulse_sec

    def execute(self, action):
        if action == "forward":
            self.driver.set_wheels(self.forward_speed, self.forward_speed)
            return

        if action == "left":
            self.driver.set_wheels(-self.turn_speed * self.turn_bias, self.turn_speed)
            time.sleep(self.pulse_sec)
            self.driver.stop()
            return

        if action == "right":
            self.driver.set_wheels(self.turn_speed, -self.turn_speed * self.turn_bias)
            time.sleep(self.pulse_sec)
            self.driver.stop()
            return

        if action == "stop":
            self.driver.stop()
            return

        raise ValueError(f"Unsupported action: {action}")


def build_handler(executor):
    class VoiceCommandHandler(BaseHTTPRequestHandler):
        def _send_json(self, code, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/voice-command":
                self._send_json(404, {"ok": False, "error": "unknown endpoint"})
                return

            length_raw = self.headers.get("Content-Length", "0")
            try:
                length = int(length_raw)
            except ValueError:
                self._send_json(400, {"ok": False, "error": "invalid content-length"})
                return

            body = self.rfile.read(length)
            try:
                data = json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._send_json(400, {"ok": False, "error": "invalid json"})
                return

            action = data.get("action")
            if not isinstance(action, str):
                self._send_json(400, {"ok": False, "error": "missing action"})
                return

            action = action.strip().lower()
            try:
                executor.execute(action)
            except ValueError as exc:
                self._send_json(400, {"ok": False, "error": str(exc)})
                return
            except Exception as exc:  # noqa: BLE001
                self._send_json(500, {"ok": False, "error": f"execution failure: {exc}"})
                return

            self._send_json(200, {"ok": True, "action": action})

        def do_GET(self):
            if self.path == "/health":
                self._send_json(200, {"ok": True, "status": "ready"})
                return
            self._send_json(404, {"ok": False, "error": "unknown endpoint"})

        def log_message(self, format_str, *args):
            print(f"[HTTP] {self.address_string()} - {format_str % args}")

    return VoiceCommandHandler


def main():
    parser = argparse.ArgumentParser(description="Tiny Duckiebot receiver for /voice-command")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Bind port (default: 8080)")
    parser.add_argument("--forward-speed", type=float, default=0.35, help="Forward wheel speed")
    parser.add_argument("--turn-speed", type=float, default=0.28, help="Turn wheel speed")
    parser.add_argument("--turn-bias", type=float, default=0.55, help="Inner wheel bias while turning")
    parser.add_argument("--turn-pulse", type=float, default=0.35, help="Seconds for each turn pulse")

    args = parser.parse_args()

    driver = SimpleMotorDriver(verbose=True)
    executor = ActionExecutor(
        driver=driver,
        forward_speed=args.forward_speed,
        turn_speed=args.turn_speed,
        turn_bias=args.turn_bias,
        pulse_sec=args.turn_pulse,
    )

    handler = build_handler(executor)
    server = HTTPServer((args.host, args.port), handler)

    print(f"Receiver listening on http://{args.host}:{args.port}")
    print("POST /voice-command with JSON: {\"action\": \"forward|left|right|stop\"}")
    print("GET  /health")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        driver.stop()
        server.server_close()
        print("Receiver stopped.")


if __name__ == "__main__":
    main()
