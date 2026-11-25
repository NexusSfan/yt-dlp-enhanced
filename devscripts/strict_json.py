"""Strict JSON decoding for local developer evidence."""

import json


MAX_JSON_BYTES = 32 * 1024 * 1024


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON member')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f'invalid JSON constant: {value}')


def loads(text):
    try:
        return json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)
    except RecursionError:
        raise ValueError('JSON nesting exceeds decoder limit') from None


def load_file(path):
    # Limit trusted-tool receipts and assignment files before allocating the entire input.
    with path.open('rb') as stream:
        data = stream.read(MAX_JSON_BYTES + 1)
    if len(data) > MAX_JSON_BYTES:
        raise ValueError('JSON file exceeds 32 MiB limit')
    return loads(data.decode('utf-8'))
