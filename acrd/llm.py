"""Claude client with explicit live/mock modes and resumable response cache.
Cache identity includes model, prompts, temperature, max_tokens, mock and schema.
A live run without an API key fails. Cached completed responses can be reused;
retries or interrupted requests may still incur charges. Mock is a software test.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import threading
import time

_lock = threading.Lock()


def extract_json(text: str) -> dict:
    """Return the first JSON object found in text (tolerates ```json fences and prose)."""
    m = re.search(r"\{.*\}", text, flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    # fallback for truncated / malformed JSON: recover "key": value pairs with regex
    pairs = dict(re.findall(r'"(\w+)"\s*:\s*(-?\d+(?:\.\d+)?)', text))
    pairs.update(re.findall(r'"(\w+)"\s*:\s*"([A-Z_]+)"', text))
    if pairs:
        return {k: (float(v) if re.fullmatch(r"-?\d+(?:\.\d+)?", v) else v) for k, v in pairs.items()}
    raise ValueError(f"No JSON object in response: {text[:200]}")


class LLM:
    def __init__(self, cache_path: str, mock: bool | None = None):
        self.cache_path = cache_path
        if mock is None:
            mock = os.getenv("ACRD_MOCK") == "1"
        if not mock and not os.getenv("ANTHROPIC_API_KEY"):
            raise SystemExit("ANTHROPIC_API_KEY is not set. Set it, or use --mock for an offline test.")
        self.mock = mock
        self.cache = {}
        os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                        if r["text"].strip():
                            self.cache[r["key"]] = r["text"]
                    except Exception:
                        pass
        if not self.mock:
            import anthropic
            self.client = anthropic.Anthropic(max_retries=6)
        self.n_calls = 0
        self.usage = {"input_tokens": 0, "output_tokens": 0}
        self.usage_by_model = {}

    def _key(self, model, system, messages, temperature, tag,max_tokens=800):
        raw = json.dumps(["final_descriptive_2",model, system, messages, temperature, tag,max_tokens,self.mock], sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def call(self, model: str, system: str, messages: list, temperature: float = 0.0,
             max_tokens: int = 800, tag: str = "", mock_fn=None) -> str:
        key = self._key(model, system, messages, temperature, tag,max_tokens)
        if key in self.cache:
            return self.cache[key]
        if self.mock:
            text = mock_fn() if mock_fn else "{}"
        else:
            text, tin, tout = self._create(model, system, messages, temperature, max_tokens)
        with _lock:
            self.n_calls += 1
            self.cache[key] = text
            rec = {"key": key, "tag": tag, "text": text, "model": model}
            if not self.mock:
                rec.update(input_tokens=tin, output_tokens=tout, ts=time.time())
                u = self.usage_by_model.setdefault(model, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
                u["calls"] += 1; u["input_tokens"] += tin; u["output_tokens"] += tout
            with open(self.cache_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        return text

    # Current Claude models reject `temperature` ("deprecated for this model"), so it is not sent;
    # models use their default sampling. It is still part of the cache key for bookkeeping.
    _temp_mode = "none"

    def _create(self, model, system, messages, temperature, max_tokens):
        import anthropic
        last_diag = ""
        for attempt in range(5):
            try:
                resp = self.client.messages.create(model=model, system=system, messages=messages,
                                                   max_tokens=max_tokens)
            except (anthropic.AuthenticationError, anthropic.PermissionDeniedError,
                    anthropic.NotFoundError, anthropic.BadRequestError):
                raise  # not retryable: wrong key / model name / request
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(2 ** attempt)
                continue
            with _lock:
                self.usage["input_tokens"] += resp.usage.input_tokens
                self.usage["output_tokens"] += resp.usage.output_tokens
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            if text.strip():
                return text, resp.usage.input_tokens, resp.usage.output_tokens
            # empty text: record why, and give the model more room if it ran out of tokens
            stop = getattr(resp, "stop_reason", None)
            last_diag = f"stop_reason={stop}, blocks={[getattr(b, 'type', '?') for b in resp.content]}, max_tokens={max_tokens}"
            if stop == "max_tokens":
                max_tokens = min(max_tokens * 3, 4000)
            elif stop == "refusal":
                return "[REFUSAL]", resp.usage.input_tokens, resp.usage.output_tokens
            time.sleep(1)
        raise RuntimeError(f"Claude API returned no text after retries ({last_diag})")

    def call_json(self, *args, **kwargs) -> dict:
        text = self.call(*args, **kwargs)
        try:
            return extract_json(text)
        except Exception:
            # one repair attempt: ask again with a stricter instruction, different tag => not cached twice
            kwargs = dict(kwargs)
            kwargs["tag"] = kwargs.get("tag", "") + ":retry"
            msgs = list(args[2]) if len(args) > 2 else list(kwargs.pop("messages"))
            msgs = msgs + [{"role": "assistant", "content": text},
                           {"role": "user", "content": "Return ONLY the JSON object, nothing else."}]
            if len(args) > 2:
                args = (args[0], args[1], msgs) + tuple(args[3:])
            else:
                kwargs["messages"] = msgs
            return extract_json(self.call(*args, **kwargs))


def mock_rng(*parts) -> random.Random:
    return random.Random(hashlib.md5("|".join(map(str, parts)).encode()).hexdigest())
