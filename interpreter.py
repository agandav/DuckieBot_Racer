# interpreter.py
#
# Parse logic:
#   1. Try GPT -> if it works, return the result
#   2. If GPT fails for any reason -> silently fall back to keyword matching
#   3. If keywords also fail -> return None and main.py will just skip that command

from openai import AzureOpenAI
import keys
import json
import re

client = AzureOpenAI(
    api_key=keys.azure_openai_key,
    api_version="2024-02-01",
    azure_endpoint=keys.azure_openai_endpoint  # e.g. "https://YOUR-RESOURCE.openai.azure.com/"
)

SYSTEM_PROMPT = """Convert spoken driving commands to JSON. Output ONLY valid JSON, nothing else.
Format: {"action": "move"|"turn"|"stop"|"lane_follow", "direction": "forward"|"backward"|"left"|"right"|null, "speed": "slow"|"normal"|"fast"|null}

Examples:
"go forward" -> {"action": "move", "direction": "forward", "speed": "normal"}
"turn left"  -> {"action": "turn", "direction": "left", "speed": null}
"stop"       -> {"action": "stop", "direction": null, "speed": null}
"follow the lane" -> {"action": "lane_follow", "direction": null, "speed": null}
"""

# ---------------------------------------------------------------------------
# Fallback — keyword matching (from duckiebot_voice_control.py)
# Only used when GPT fails or is unavailable
# ---------------------------------------------------------------------------
def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-zA-Z0-9 ]+", " ", text.lower()).split())


def _keyword_fallback(text: str) -> dict | None:
    t = _normalize(text)
    words = t.split()

    # stop — highest priority, check first
    if any(w in words for w in ["stop", "halt", "brake", "freeze", "pause"]):
        return {"action": "stop", "direction": None, "speed": None}

    # turns — check multi-word first, then single word
    if "turn left" in t or "left" in words:
        return {"action": "turn", "direction": "left", "speed": None}
    if "turn right" in t or "right" in words:
        return {"action": "turn", "direction": "right", "speed": None}

    # forward
    if any(w in words for w in ["forward", "go", "straight", "ahead", "move"]):
        return {"action": "move", "direction": "forward", "speed": "normal"}

    # backward
    if any(w in words for w in ["backward", "back", "reverse"]):
        return {"action": "move", "direction": "backward", "speed": "normal"}

    # speed adjust
    if any(w in words for w in ["faster", "speed"]):
        return {"action": "adjust", "direction": None, "speed": "fast"}
    if any(w in words for w in ["slower", "slow"]):
        return {"action": "adjust", "direction": None, "speed": "slow"}

    # lane follow
    if "lane" in words:
        return {"action": "lane_follow", "direction": None, "speed": None}

    return None  # nothing matched


# ---------------------------------------------------------------------------
# Main parse function — GPT first, keyword fallback second
# ---------------------------------------------------------------------------
def parse(text: str) -> dict | None:
    # --- Try LLM first ---
    try:
        response = client.chat.completions.create(
            model=keys.azure_openai_deployment,  # your deployment name e.g. "gpt-4o"
            max_tokens=60,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ]
        )
        result = json.loads(response.choices[0].message.content)
        print("[LLM] Parsed via GPT")
        return result

    except Exception as e:
        print(f"[LLM] GPT failed ({e}) — using keyword fallback")

    # --- Fallback to keywords ---
    result = _keyword_fallback(text)
    if result:
        print(f"[LLM] Parsed via fallback: {result}")
    else:
        print("[LLM] No match found in fallback either")
    return result