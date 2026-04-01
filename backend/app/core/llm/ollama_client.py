import os
import requests
from typing import Optional

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_TIMEOUT_SECS = float(os.getenv("OLLAMA_TIMEOUT_SECS", "12"))

def ollama_generate(prompt: str) -> Optional[str]:
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 512,
                },
            },
            timeout=OLLAMA_TIMEOUT_SECS,
        )
        r.raise_for_status()
        data = r.json()
        text = (data.get("response") or "").strip()
        return text or None
    except Exception:
        return None
