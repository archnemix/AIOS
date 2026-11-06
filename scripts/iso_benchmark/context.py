"""Long-context and shared-prefix checks using the native completion endpoint."""
import time


def complete(client, prompt, cache):
    start = time.monotonic()
    response = client.request('/completion', {'prompt': prompt, 'n_predict': 1, 'temperature': 0,
                                               'cache_prompt': cache}, timeout=1200)
    timings = response.get('timings', {})
    result = {'wall_seconds': time.monotonic() - start, 'input_tokens': len(prompt),
              'tokens_evaluated': response.get('tokens_evaluated'),
              'prompt_tokens_processed': timings.get('prompt_n'),
              'prompt_ms': timings.get('prompt_ms'), 'truncated': response.get('truncated'),
              'generated_tokens': response.get('tokens_predicted')}
    if result['tokens_evaluated'] != len(prompt) or result['truncated'] is not False:
        raise RuntimeError('long prompt was truncated or not fully accepted')
    if result['generated_tokens'] != 1 or not isinstance(result['prompt_tokens_processed'], int):
        raise RuntimeError('completion or prompt timing is missing')
    return result


def shared_prefix(client, prefix_length=4096, suffix_length=16):
    # Token IDs avoid ambiguity from string tokenization or chat templates.
    tokens = client.request('/tokenize', {'content': ' hello world', 'add_special': False})['tokens']
    if len(tokens) < 2:
        raise RuntimeError('expected at least two tokenizer tokens')
    prefix = [tokens[0]] * prefix_length
    target = prefix + [tokens[-1]] * suffix_length
    cold = complete(client, target, False)
    complete(client, prefix, False)  # Restore the identical prefix in the slot.
    cached = complete(client, target, True)
    if cached['prompt_tokens_processed'] >= cold['prompt_tokens_processed']:
        raise RuntimeError('the server did not reuse the shared prompt prefix')
    return {'cold': cold, 'cached': cached,
            'wall_speedup': cold['wall_seconds'] / cached['wall_seconds']}
