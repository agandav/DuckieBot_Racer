import time
import speech_to_text.stt as stt
from text_commands.llm import parse_commands      # for the LLM module
from robot_control.controller import execute_commands


def on_speech(text: str):
    """Called automatically by STT every time a phrase is recognized."""
    print(f"\nHeard: {text}")

    commands = parse_commands(text)

    if not commands:
        print("No commands parsed.")
        return

    print(f"Commands: {commands}")
    execute_commands(commands)


if __name__ == "__main__":
    stt.start(on_recognized=on_speech)
    print("Listening... speak to drive. Ctrl+C to stop.")

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping...")
        stt.stop()