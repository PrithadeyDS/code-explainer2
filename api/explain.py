from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
import urllib.error

PROMPTS = {
    "explain": """You are a friendly coding tutor. Explain the following {lang} code to a beginner.
Respond ONLY with valid JSON (no markdown, no backticks) in exactly this shape:
{{
  "what_it_does": "...",
  "how_it_works": "...",
  "time_complexity": "...",
  "space_complexity": "...",
  "key_parts": ["...", "..."]
}}

Code:
{code}""",

    "improve": """You are a senior software engineer. Review the following {lang} code and suggest concrete improvements
(readability, naming, structure, edge cases, bugs). Respond ONLY with valid JSON (no markdown, no backticks):
{{
  "issues": ["...", "..."],
  "suggestions": ["...", "..."]
}}

Code:
{code}""",

    "optimize": """You are a senior software engineer. Rewrite the following {lang} code to be more optimized
(better time/space complexity where possible). Respond ONLY with valid JSON (no markdown, no backticks):
{{
  "optimized_code": "...",
  "what_changed": "...",
  "new_time_complexity": "...",
  "new_space_complexity": "..."
}}

Code:
{code}"""
}


def call_claude(prompt: str) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")

    body = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    text = "".join(block.get("text", "") for block in data.get("content", []))
    return text


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            payload = json.loads(raw or b"{}")

            code = payload.get("code", "").strip()
            lang = payload.get("language", "Python")
            action = payload.get("action", "explain")

            if not code:
                return self._send_json(400, {"error": "No code provided"})
            if action not in PROMPTS:
                return self._send_json(400, {"error": "Invalid action"})

            prompt = PROMPTS[action].format(lang=lang, code=code)
            raw_text = call_claude(prompt)

            cleaned = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError:
                parsed = {"raw": raw_text}

            return self._send_json(200, {"result": parsed})

        except urllib.error.HTTPError as e:
            return self._send_json(502, {"error": f"LLM API error: {e.read().decode('utf-8', 'ignore')}"})
        except Exception as e:
            return self._send_json(500, {"error": str(e)})