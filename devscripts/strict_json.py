"""Strict JSON decoding for local developer evidence."""

import json


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
    limit = 32 * 1024 * 1024
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('JSON file exceeds 32 MiB limit')
    return loads(data.decode('utf-8'))
