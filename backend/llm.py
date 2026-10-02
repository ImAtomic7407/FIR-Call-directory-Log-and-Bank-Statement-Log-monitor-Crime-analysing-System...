"""LiteLLM client for the remote LAN laptop (Qwen3-4B Q4 via Ollama). Always optional: callers fall back to rules.

Config (env or .env):
  LLM_MODEL      e.g. ollama_chat/qwen3:4b
  LLM_API_BASE   e.g. http://192.168.1.50:11434
  LLM_API_KEY    key for the LiteLLM proxy (omit for Ollama)
  LLM_TIMEOUT    seconds (default 25)
  LLM_ENABLED    1/0 (default 1 if LLM_API_BASE is set)
"""
import json, os, re, socket, time
from urllib.parse import urlparse
from pathlib import Path

for line in (Path(__file__).parent / ".env").read_text().splitlines() if (Path(__file__).parent / ".env").exists() else []:
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

MODEL = lambda: os.getenv("LLM_MODEL", "ollama_chat/qwen3:4b")
BASE = lambda: os.getenv("LLM_API_BASE", "")
KEY = lambda: os.getenv("LLM_API_KEY") or None
TIMEOUT = lambda: float(os.getenv("LLM_TIMEOUT", "25"))
_last_error = {"msg": None, "ok": False}
_down_until = [0.0]  # after a failed connection, skip the model for a while so answers stay fast


def _reachable():
    """Quick TCP check (1.5s). A recent failure is remembered for 60s."""
    if time.time() < _down_until[0]:
        return False
    u = urlparse(BASE())
    try:
        socket.create_connection((u.hostname, u.port or (443 if u.scheme == "https" else 80)), timeout=1.5).close()
        return True
    except OSError as e:
        _down_until[0] = time.time() + 60
        _last_error["ok"] = False; _last_error["msg"] = f"unreachable: {u.hostname}:{u.port} ({e.__class__.__name__})"
        return False


def enabled():
    return bool(BASE()) and os.getenv("LLM_ENABLED", "1") != "0"


def status():
    return dict(enabled=enabled(), model=MODEL(), api_base=BASE() or None, last_error=_last_error["msg"], reachable=_last_error["ok"])


def complete(messages, max_tokens=400, temperature=0.0):
    """Returns text or None (never raises)."""
    if not enabled() or not _reachable():
        return None
    try:
        import litellm
        litellm.suppress_debug_info = True
        msgs = [dict(m) for m in messages]
        msgs[-1]["content"] = msgs[-1]["content"] + "\n/no_think"  # Qwen3: skip chain-of-thought for speed
        r = litellm.completion(model=MODEL(), api_base=BASE(), api_key=KEY(), messages=msgs, temperature=temperature,
                               max_tokens=max_tokens, timeout=TIMEOUT())
        txt = r.choices[0].message.content or ""
        txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S).strip()
        _last_error["msg"] = None; _last_error["ok"] = True
        return txt
    except Exception as e:  # network down, model missing, timeout...
        _last_error["ok"] = False
        if isinstance(e, TimeoutError) or "Timeout" in type(e).__name__: _down_until[0] = time.time() + 30
        _last_error["msg"] = f"{type(e).__name__}: {str(e)[:160]}"
        return None


def complete_json(messages, **kw):
    txt = complete(messages, **kw)
    if not txt:
        return None
    m = re.search(r"\{.*\}", txt, flags=re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except Exception:
        return None
