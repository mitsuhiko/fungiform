# -*- coding: utf-8 -*-
"""
    fungiform.csrf
    ~~~~~~~~~~~~~~

    CSRF protection for Fungiform.

    :copyright: (c) 2010 by the Fungiform Team.
    :license: BSD, see LICENSE for more details.
"""
import os
import hmac
from functools import update_wrapper
from zlib import adler32
try:
    from hashlib import sha1
except ImportError:
    from sha import new as sha1


#: the maximum number of csrf tokens kept in the session.  After that, the
#: oldest item is deleted
MAX_CSRF_TOKENS = 4


def csrf_url_hash(url):
    """A hash for a URL for the CSRF system."""
    if isinstance(url, unicode):
        url = url.encode('utf-8')
    return int(adler32(url) & 0xffffffff)


def random_token():
    """Creates a random token.  10 byte in size."""
    return os.urandom(10)


def get_csrf_token(session, url, force_update=False):
    """Return a CSRF token."""
    url_hash = csrf_url_hash(url)
    tokens = session.setdefault('csrf_tokens', [])
    token = None

    if not force_update:
        for stored_hash, stored_token in tokens:
            if stored_hash == url_hash:
                token = stored_token
                break
    if token is None:
        if len(tokens) >= MAX_CSRF_TOKENS:
            tokens.pop(0)

        token = random_token()
        tokens.append((url_hash, token))
        session['csrf_tokens'] = tokens

    return token.encode('hex')


def invalidate_csrf_token(session, url):
    """Clears the CSRF token for the given URL."""
    url_hash = csrf_url_hash(url)
    tokens = session.get('csrf_tokens', None)
    if not tokens:
        return
    session['csrf_tokens'] = [(h, t) for h, t in tokens if h != url_hash]
