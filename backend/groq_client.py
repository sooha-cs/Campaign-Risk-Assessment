import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

URL = "https://api.groq.com/openai/v1/chat/completions"


def call_groq(messages, json_mode=False, temperature=0.2):
    """Call Groq chat completions. json_mode=True forces JSON-only output."""
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY missing in .env")

    body = {
        "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    res = requests.post(
        URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=body,
        timeout=60,
    )
    if not res.ok:
        raise RuntimeError(f"Groq {res.status_code}: {res.text}")
    return res.json()["choices"][0]["message"]["content"]


def call_groq_json(messages, **kwargs):
    """Convenience: returns the parsed JSON dict."""
    return json.loads(call_groq(messages, json_mode=True, **kwargs))
