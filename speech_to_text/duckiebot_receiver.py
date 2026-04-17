import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import controller
import camera


class SimpleMotorDriver:
    def __init__(self, verbose=True):
        self.verbose = verbose

    def set_wheels(self, left, right):
        if self.verbose:
            print(f"[MOTOR] left={left:.2f} right={right:.2f}")
        if left > 0 and right > 0:
            controller.execute({"action": "move", "direction": "forward", "speed": "normal"})
        elif left < 0 and right < 0:
            controller.execute({"action": "move", "direction": "backward", "speed": "normal"})
        elif left <= 0 and right > 0:
            controller.execute({"action": "turn", "direction": "left", "speed": None})
        elif left > 0 and right <= 0:
            controller.execute({"action": "turn", "direction": "right", "speed": None})
        else:
            controller.execute({"action": "stop", "direction": None, "speed": None})

    def stop(self):
        print("[MOTOR] STOP")
        controller.execute({"action": "stop", "direction": None, "speed": None})


class ActionExecutor:
    def __init__(self, driver, forward_speed=0.35, turn_speed=0.28, turn_bias=0.55, pulse_sec=0.35):
        self.driver     = driver
        self.forward_speed = forward_speed
        self.turn_speed    = turn_speed
        self.turn_bias     = turn_bias
        self.pulse_sec     = pulse_sec

    def execute(self, action):
        if action in ("forward", "move"):
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
        if action == "backward":
            self.driver.set_wheels(-self.forward_speed, -self.forward_speed)
            return
        if action in ("stop", "lane_follow"):
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

            action    = data.get("action")
            direction = data.get("direction")

            if not isinstance(action, str):
                self._send_json(400, {"ok": False, "error": "missing action"})
                return

            action = action.strip().lower()

            # map action+direction to simple action string
            if action == "move" and direction == "backward":
                action = "backward"
            elif action == "turn" and direction == "right":
                action = "right"
            elif action == "turn" and direction == "left":
                action = "left"

            try:
                executor.execute(action)
            except ValueError as exc:
                self._send_json(400, {"ok": False, "error": str(exc)})
                return
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": f"execution failure: {exc}"})
                return

            self._send_json(200, {"ok": True, "action": action})

        def do_GET(self):
            # ── /health ───────────────────────────────────────────────
            if self.path == "/health":
                self._send_json(200, {"ok": True, "status": "ready"})
                return

            # ── /camera-color ─────────────────────────────────────────
            # Returns what the robot camera currently sees:
            #   color:    "red" | "yellow" | "green" | "none"
            #   position: "left" | "right" | "center"  (yellow tape position)
            if self.path == "/camera-color":
                try:
                    frame    = camera.get_frame()
                    color    = camera.get_camera_color(frame)
                    position = camera.get_yellow_position(frame)
                    self._send_json(200, {
                        "ok":       True,
                        "color":    color,
                        "position": position,
                    })
                except Exception as exc:
                    self._send_json(500, {"ok": False, "error": str(exc)})
                return

            self._send_json(404, {"ok": False, "error": "unknown endpoint"})

        def log_message(self, format_str, *args):
            print(f"[HTTP] {self.address_string()} - {format_str % args}")

    return VoiceCommandHandler


def main():
    parser = argparse.ArgumentParser(description="Duckiebot receiver")
    parser.add_argument("--host",          default="0.0.0.0")
    parser.add_argument("--port",          type=int,   default=8888)
    parser.add_argument("--forward-speed", type=float, default=0.35)
    parser.add_argument("--turn-speed",    type=float, default=0.28)
    parser.add_argument("--turn-bias",     type=float, default=0.55)
    parser.add_argument("--turn-pulse",    type=float, default=0.35)
    args = parser.parse_args()

    # initialize camera on startup
    print("[INIT] Starting camera...")
    camera.init_camera()

    driver = SimpleMotorDriver(verbose=True)
    executor = ActionExecutor(
        driver=driver,
        forward_speed=args.forward_speed,
        turn_speed=args.turn_speed,
        turn_bias=args.turn_bias,
        pulse_sec=args.turn_pulse,
    )

    handler = build_handler(executor)
    server  = HTTPServer((args.host, args.port), handler)

    print(f"Receiver listening on http://{args.host}:{args.port}")
    print("POST /voice-command  — move robot")
    print("GET  /camera-color   — get camera reading")
    print("GET  /health         — health check")

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