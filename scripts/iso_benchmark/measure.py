"""Repeatable inference and context checks against two running servers."""

import statistics
import time

PROMPT = ("Explain how a CPU processes a small language model. " * 4).strip()
METRICS = ("ttft_seconds", "wall_seconds", "prompt_tokens_per_second", "output_tokens_per_second")


def run_comparison(host, guest):
    # Warm both servers, then alternate order to reduce time-order bias.
    host.stream_completion(PROMPT)
    guest.stream_completion(PROMPT)
    samples = {"github_linux": [], "aios_vm": []}
    for order in (("github_linux", "aios_vm"), ("aios_vm", "github_linux"),
                  ("github_linux", "aios_vm")):
        for name in order:
            samples[name].append({"github_linux": host, "aios_vm": guest}[name].stream_completion(PROMPT))
    medians = {name: {key: statistics.median(sample[key] for sample in values)
                      for key in METRICS} for name, values in samples.items()}
    return {"samples": samples, "medians": medians}


def check_context(client, token_count=2048, timeout=300):
    tokens = client.request("/tokenize", {"content": " hello", "add_special": False})["tokens"]
    if not tokens:
        raise RuntimeError("tokenizer returned no tokens")
    started = time.monotonic()
    result = client.request("/completion", {"prompt": [tokens[-1]] * token_count, "n_predict": 1,
                                            "temperature": 0, "cache_prompt": False}, timeout=timeout)
    return {"input_tokens": token_count, "tokens_evaluated": result.get("tokens_evaluated"),
            "truncated": result.get("truncated"), "wall_seconds": time.monotonic() - started,
            "passed": result.get("tokens_evaluated") == token_count and result.get("truncated") is False}
