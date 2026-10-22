import base64
import hashlib
import hmac
import json
import os
import re
import time
from .validation import fail, integer

ROLES = ('admin', 'teacher', 'student', 'ai_service')


def hash_password(password):
    salt = os.urandom(16).hex()
    key = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=64)
    return f'scrypt:{salt}:{key.hex()}'


def verify_password(password, encoded):
    parts = encoded.split(':')
    if len(parts) != 3 or parts[0] != 'scrypt' or not re.fullmatch('[a-f0-9]{32}', parts[1]) or not re.fullmatch('[a-f0-9]{128}', parts[2]):
        return False
    key = hashlib.scrypt(password.encode(), salt=parts[1].encode(), n=16384, r=8, p=1, dklen=64)
    return hmac.compare_digest(key.hex(), parts[2])


def ai_key():
    key = os.getenv('AI_SERVICE_KEY', '')
    if len(key) < 32:
        fail('Configure AI_SERVICE_KEY in BE and AI', 503)
    return key


def b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def sign_ticket(student_id, user_id):
    encoded = b64(json.dumps({'studentId': student_id, 'userId': user_id, 'expires': int(time.time() * 1000) + 900000}, separators=(',', ':')).encode())
    return encoded + '.' + b64(hmac.digest(ai_key().encode(), encoded.encode(), 'sha256'))


def verify_ticket(value, user_id):
    key = ai_key()
    if not isinstance(value, str) or len(value) > 2000:
        fail('Recognition ticket required')
    try:
        encoded, signature = value.split('.')
        expected = b64(hmac.digest(key.encode(), encoded.encode(), 'sha256'))
        if not hmac.compare_digest(signature.encode(), expected.encode()):
            raise ValueError()
        ticket = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
        if not isinstance(ticket, dict):
            raise ValueError()
        integer(ticket.get('studentId'), 'studentId')
        if ticket.get('userId') != user_id or type(ticket.get('expires')) not in (int, float) or not time.time() * 1000 <= ticket['expires'] < float('inf'):
            fail('Recognition expired or belongs to another account')
        return ticket
    except (ValueError, TypeError, KeyError):
        fail('Invalid recognition ticket')
