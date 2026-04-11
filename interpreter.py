# interpreter.py
from openai import AzureOpenAI
import keys
import json

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

def parse(text: str) -> dict:
    response = client.chat.completions.create(
        model=keys.azure_openai_deployment,  # your deployment name, e.g. "gpt-4o"
        max_tokens=60,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text}
        ]
    )
    return json.loads(response.choices[0].message.content)