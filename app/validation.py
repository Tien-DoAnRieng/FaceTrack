import re
from datetime import datetime, timezone
from fastapi import HTTPException


def fail(message, status=400):
    raise HTTPException(status, message)


def obj(value, allowed):
    if not isinstance(value, dict):
        fail('Expected a JSON object')
    extra = set(value) - set(allowed)
    if extra:
        fail('Unsupported fields: ' + ', '.join(sorted(extra)))
    return value


def text(value, field, maximum=200, known=False):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        fail(f'{field} must be a nonempty string of at most {maximum} characters')
    value = value.strip()
    if known and value.lower() == 'unknown':
        fail('Unknown identities cannot be stored')
    return value


def integer(value, field, query=False):
    if query and isinstance(value, str) and re.fullmatch(r'[1-9]\d*', value):
        value = int(value)
    if type(value) is not int or not 1 <= value <= 9007199254740991:
        fail(f'{field} must be a positive integer')
    return value


def choice(value, field, values):
    if value not in values:
        fail(f'{field} must be one of: {", ".join(values)}')
    return value


def iso(value):
    return value.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def utc(value, field):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z|[+-]\d{2}:\d{2})', value):
        fail(f'{field} must be an ISO 8601 timestamp with timezone')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.year < 100:
            raise ValueError()
        return iso(parsed)
    except (ValueError, OverflowError):
        fail(f'{field} is not a valid timestamp')
