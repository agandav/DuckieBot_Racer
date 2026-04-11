# DuckieBot_Racer

Simple speech-driven control wrapper for Duckiebot.

## Files

- `speech_to_text/sst.py`: Azure Speech-to-Text listener
- `speech_to_text/duckiebot_voice_control.py`: voice command parser + simple command sender
- `speech_to_text/duckiebot_receiver.py`: tiny robot-side HTTP receiver (`/voice-command`)

## 1) Setup

1. Put Azure keys in `.env` (already read by `keys.py`).
2. Install dependencies:

```bash
pip install -r requirements.txt
```

If you do not have a `requirements.txt`, install at least:

```bash
pip install azure-cognitiveservices-speech python-dotenv
```

## 2) Run in simulation mode (recommended first)

```bash
python speech_to_text/duckiebot_voice_control.py --dry-run
```

Say commands like: `forward`, `left`, `right`, `stop`.

## 3) Run with a Duckiebot hostname

```bash
python speech_to_text/duckiebot_voice_control.py --hostname duckiebot-01.local
```

This sends POST requests to:

`http://<hostname>:8080/voice-command`

Payload example:

```json
{"action": "left"}
```

You need a service on the robot listening on that endpoint.

## 4) Run robot-side receiver

On the Duckiebot side (or any host pretending to be it), run:

```bash
python speech_to_text/duckiebot_receiver.py --host 0.0.0.0 --port 8080
```

Test from your laptop before STT:

```bash
curl -X POST http://duckiebot-01.local:8080/voice-command -H "Content-Type: application/json" -d "{\"action\":\"left\"}"
```

Health check:

```bash
curl http://duckiebot-01.local:8080/health
```

By default, the receiver prints wheel commands. Replace `SimpleMotorDriver.set_wheels(...)` in `speech_to_text/duckiebot_receiver.py` with your real motor API call.

## Hostname not showing up? (Windows quick checks)

1. Verify your PC and Duckiebot are on the same network.
2. Try mDNS name lookup:

```powershell
ping duckiebot-01.local
```

3. If `.local` names do not resolve on Windows, install Bonjour Print Services (Apple) to add mDNS support.
4. Find the robot IP from your router DHCP list, then use IP directly:

```bash
python speech_to_text/duckiebot_voice_control.py --hostname 192.168.1.42
```

5. If you can SSH by IP but not hostname, the issue is name resolution, not robot connectivity.

## Notes

- This is intentionally simple for homework prototyping.
- Command spam is limited with a short cooldown (default `0.6s`).