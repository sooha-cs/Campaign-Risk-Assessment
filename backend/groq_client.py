import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

URL = "https://api.groq.com/openai/v1/chat/completions"

# Free tier for gpt-oss-120b: 30 req/min, 1K req/day, 8K tokens/min, 200K tokens/day.
# Groq counts input + the requested max output against the per-minute limit, so we size
# max_completion_tokens from the prompt length instead of using a big fixed number.
TPM_BUDGET = int(os.getenv("GROQ_TPM_BUDGET", "7500"))
MAX_OUT_CAP = int(os.getenv("GROQ_MAX_TOKENS", "4096"))
MIN_OUT = 1200

_session_tokens = 0  # running total of tokens used since the server started


class GroqError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def _extract_json_text(text):
    """Pull the JSON object out of a reply that may have ``` fences or extra words around it."""
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


def extract_json(text):
    """Parse the AI's reply into a Python object, tolerating code fences and extra words."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(_extract_json_text(text))


def _max_output_tokens(messages):
    est_input = int(len(json.dumps(messages)) / 3)  # rough, on the safe side
    return max(MIN_OUT, min(MAX_OUT_CAP, TPM_BUDGET - est_input))


def call_groq(messages, json_mode=False, temperature=0.2):
    """Call Groq chat completions. json_mode=True asks for JSON-only output.

    Free-tier friendly:
      - max_completion_tokens is sized from the prompt so one request never exceeds the 8K/min limit
      - reasoning_effort="low" (gpt-oss only) so the model does not burn tokens thinking
      - if Groq says json_validate_failed but includes the text it generated, we use that text
        instead of spending another request
      - token usage is printed after every call
    """
    global _session_tokens
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise GroqError("GROQ_API_KEY missing in .env", 401)

    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_completion_tokens": _max_output_tokens(messages),
    }
    if "gpt-oss" in model:
        body["reasoning_effort"] = os.getenv("GROQ_REASONING_EFFORT", "low")
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    try:
        res = requests.post(
            URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body,
            timeout=120,
        )
    except requests.RequestException as e:
        raise GroqError(f"Network error: {e}") from e

    if res.status_code == 400 and "json_validate_failed" in res.text:
        try:
            salvaged = (res.json().get("error") or {}).get("failed_generation") or ""
        except ValueError:
            salvaged = ""
        if salvaged.strip():
            return salvaged  # parsed/validated by the caller; no extra request spent
        raise GroqError(
            "Groq returned no usable JSON (the model probably ran out of output tokens while thinking). "
            "Raise GROQ_MAX_TOKENS a little if this repeats.", 400)

    if not res.ok:
        if res.status_code in (413, 429):
            raise GroqError(f"Groq rate limit reached (free tier: 8K tokens/min, 200K/day). "
                            f"Wait about a minute and try again. Details: {res.text[:200]}", res.status_code)
        raise GroqError(f"Groq {res.status_code}: {res.text}", res.status_code)

    data = res.json()
    usage = data.get("usage") or {}
    _session_tokens += usage.get("total_tokens", 0)
    print(f"[groq] prompt={usage.get('prompt_tokens')} completion={usage.get('completion_tokens')} "
          f"max_out={body['max_completion_tokens']} | this session: {_session_tokens} tokens (daily limit 200K)", flush=True)

    content = data["choices"][0]["message"].get("content")
    if not content:
        raise GroqError("Groq returned an empty response (the model may have used all output tokens thinking)")
    return content


def call_groq_json(messages, **kwargs):
    """Convenience: returns the parsed JSON dict."""
    return extract_json(call_groq(messages, json_mode=True, **kwargs))
