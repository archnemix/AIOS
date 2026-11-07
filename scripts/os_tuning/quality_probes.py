"""Tiny fixed-answer smoke checks; not a general model-quality evaluation."""
import re

# Fixed, public, simple facts; accepted spellings only. Model answers may be
# correct in forms the strict exact-match scorer fails to recognize.
PROBES = (
    ('What is 2 plus 2? Reply with a single number.', ('4', 'four')),
    ('What is 3 plus 5? Reply with a single number.', ('8', 'eight')),
    ('What is the capital of France? Reply with one word.', ('paris',)),
    ('What is the capital of Japan? Reply with one word.', ('tokyo',)),
    ('What color is a clear daytime sky? Reply with one word.', ('blue',)),
    ('How many days are in a week? Reply with a single number.', ('7', 'seven')),
    ('How many months are in a year? Reply with a single number.', ('12', 'twelve')),
    ('What planet do we live on? Reply with one word.', ('earth',)),
    ('What is the opposite of hot? Reply with one word.', ('cold',)),
    ('Which animal says meow? Reply with one word.', ('cat',)),
)


def first_word(text):
    match = re.search(r"[A-Za-z0-9]+", text)
    return match.group(0).lower() if match else ''


def run(client):
    results = []
    for question, accepted in PROBES:
        result = client.request('/v1/chat/completions', {'messages': [{'role': 'user', 'content': question}],
                                'max_tokens': 12, 'temperature': 0}, timeout=180)
        answer = result['choices'][0]['message']['content']
        results.append({'question': question, 'answer': answer, 'accepted_first_words': accepted,
                        'first_word_matches': first_word(answer) in accepted})
    return results
