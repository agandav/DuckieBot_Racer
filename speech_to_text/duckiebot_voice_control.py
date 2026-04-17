" Duckiebot Voice Control using Speech-to-Text. This script listens for recognized speech, parses it into high-level commands, and sends them to the Duckiebot via HTTP POST requests. "
" It uses a simple keyword-based approach for parsing commands, and includes a cooldown mechanism to prevent spamming the robot with too many commands in quick succession. "
" Note: This is a basic implementation for demonstration purposes. In a production system, you would want to add more robust error handling, support for more complex commands, and possibly a more sophisticated natural language understanding component. "

import argparse
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request

import stt


# Keep this simple: map speech to one high-level action at a time.
VOICE_TO_ACTION = {
    "forward": "forward",  "go": "forward",   "straight": "forward",
    "ahead": "forward",    "move": "forward",
    "backward": "backward", "back": "backward", "reverse": "backward",
    "left": "left",        "left": "left",
    "right": "right",
    "stop": "stop",        "halt": "stop",     "brake": "stop",
    "freeze": "stop",      "pause": "stop",
}


def _normalize_text(text):
    clean = re.sub(r"[^a-zA-Z0-9 ]+", " ", text.lower())
    return " ".join(clean.split())


def parse_action(text):
    normalized = _normalize_text(text)
    words = normalized.split()

    # multi-word checks FIRST — before single word loop
    if "turn left"  in normalized: return "left"
    if "turn right" in normalized: return "right"
    if "go back"    in normalized: return "backward"
    if "back up"    in normalized: return "backward"
    if "go forward" in normalized: return "forward"
    if "go straight" in normalized: return "forward"
    if "speed up"   in normalized: return "faster"
    if "slow down"  in normalized: return "slower"


    for word in words:
        if word in VOICE_TO_ACTION:
            return VOICE_TO_ACTION[word]

    return None


def send_http_command(hostname, action, timeout=2.0):
    payload = json.dumps({"action": action}).encode("utf-8")
    req = urllib.request.Request(
        url=f"http://{hostname}:8080/voice-command",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8", errors="ignore")


class VoiceController:
    def __init__(self, hostname=None, dry_run=True, cooldown=0.6):
        self.hostname = hostname
        self.dry_run = dry_run
        self.cooldown = cooldown
        self._last_command_time = 0.0
        self._stop_event = threading.Event()

    def _can_send(self):
        return (time.time() - self._last_command_time) >= self.cooldown

    def _dispatch(self, action):
        if not self._can_send():
            return

        self._last_command_time = time.time()

        if self.dry_run:
            print(f"[SIM] action={action}")
            return

        if not self.hostname:
            print("[ERR] hostname is required unless --dry-run is enabled")
            return

        try:
            status, body = send_http_command(self.hostname, action)
            print(f"[HTTP] action={action} status={status} body={body}")
        except urllib.error.URLError as exc:
            print(f"[ERR] failed to reach host '{self.hostname}': {exc}")

    def on_recognized(self, text):
        print(f"[STT] {text}")
        action = parse_action(text)
        if action:
            self._dispatch(action)

    def run(self):
        stt.start(on_recognized=self.on_recognized)
        print("Voice control started. Say: forward, left, right, or stop.")
        if self.dry_run:
            print("Running in simulation mode (--dry-run).")
        else:
            print(f"Sending commands to http://{self.hostname}:8080/voice-command")

        try:
            while not self._stop_event.is_set():
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            stt.stop()
            print("Voice control stopped.")



def main(argv=None):
    parser = argparse.ArgumentParser(description="Simple voice control wrapper for Duckiebot")
    parser.add_argument(
        "--hostname",
        default=None,
        help="Duckiebot hostname or IP (example: duckiebot-xx.local)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not send network commands; only print parsed actions",
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=0.6,
        help="Minimum seconds between command dispatches",
    )

    args = parser.parse_args(argv)

    controller = VoiceController(
        hostname=args.hostname,
        dry_run=args.dry_run,
        cooldown=args.cooldown,
    )
    controller.run()


if __name__ == "__main__":
    sys.exit(main())
