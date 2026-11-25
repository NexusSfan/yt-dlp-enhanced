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
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)
