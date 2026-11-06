"""Minimal llama.cpp API client used by the comparison."""

import json
import time
import urllib.request


class Client:
    def __init__(self, port, token):
        self.base = f"http://127.0.0.1:{port}"
        self.token = token

    def request(self, path, payload=None, timeout=120):
        data = None if payload is None else json.dumps(payload).encode()
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        req = urllib.request.Request(self.base + path, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)

    def stream_completion(self, prompt):
        payload = {"prompt": prompt, "n_predict": 32, "temperature": 0,
                   "ignore_eos": True, "cache_prompt": False, "stream": True}
        req = urllib.request.Request(self.base + "/completion", data=json.dumps(payload).encode(),
                                     headers={"Authorization": f"Bearer {self.token}",
                                              "Content-Type": "application/json"})
        started = time.monotonic()
        first = None
        final = None
        with urllib.request.urlopen(req, timeout=600) as response:
            for raw in response:
                if not raw.startswith(b"data: "):
                    continue
                event = json.loads(raw[6:])
                if event.get("content") and first is None:
                    first = time.monotonic() - started
                if event.get("stop"):
                    final = event
                    break
        if first is None or final is None or final.get("truncated"):
            raise RuntimeError("incomplete or truncated streaming completion")
        timings = final["timings"]
        return {"ttft_seconds": first, "wall_seconds": time.monotonic() - started,
                "prompt_tokens": timings["prompt_n"], "output_tokens": timings["predicted_n"],
                "prompt_tokens_per_second": timings["prompt_per_second"],
                "output_tokens_per_second": timings["predicted_per_second"]}
