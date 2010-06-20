# -*- coding: utf-8 -*-
"""
    fungiform.redirects
    ~~~~~~~~~~~~~~~~~~~

    Helps with redirects in WSGI applications.  Helps to avoid security
    problems.

    :copyright: (c) 2010 by the Fungiform Team.
    :license: BSD, see LICENSE for more details.
"""
import urllib
from itertools import chain
from urlparse import urlparse, urlsplit, urljoin
from cgi import parse_qsl as urldecode
from fnmatch import fnmatch


def get_current_url(environ, root_only=False):
    """A handy helper function that recreates the full URL for the current
    request or parts of it.  Here an example:

    >>> def create_environ(path, base_url):
    ...     scheme, netloc, script_root, _, _ = urlsplit(base_url)
    ...     _, _, path_info, qs, anchor = urlsplit(path)
    ...     return {'SCRIPT_NAME':      script_root,
    ...             'PATH_INFO':        path_info,
    ...             'QUERY_STRING':     qs,
    ...             'HTTP_HOST':        netloc,
    ...             'wsgi.url_scheme':  scheme}
    >>> env = create_environ("/?param=foo", "http://localhost/script")
    >>> get_current_url(env)
    'http://localhost/script/?param=foo'
    >>> get_current_url(env, root_only=True)
    'http://localhost/script/'

    :param environ: the WSGI environment to get the current URL from.
    :param root_only: set `True` if you only want the root URL.
    """
    tmp = [environ['wsgi.url_scheme'], '://', get_host(environ)]
    cat = tmp.append
    cat(urllib.quote(environ.get('SCRIPT_NAME', '').rstrip('/')))
    if root_only:
        cat('/')
    else:
        cat(urllib.quote('/' + environ.get('PATH_INFO', '').lstrip('/')))
        qs = environ.get('QUERY_STRING')
        if qs:
            cat('?' + qs)
    return ''.join(tmp)


def get_host(environ):
    """Return the real host for the given WSGI environment.  This takes care
    of the `X-Forwarded-Host` header.

    :param environ: the WSGI environment to get the host of.
    """
    if 'HTTP_X_FORWARDED_HOST' in environ:
        return environ['HTTP_X_FORWARDED_HOST']
    elif 'HTTP_HOST' in environ:
        return environ['HTTP_HOST']
    result = environ['SERVER_NAME']
    if (environ['wsgi.url_scheme'], environ['SERVER_PORT']) not \
       in (('https', '443'), ('http', '80')):
        result += ':' + environ['SERVER_PORT']
    return result


def get_redirect_target(environ, user_url=None, invalid_targets=(),
                        allowed_redirects=None):
    """Check the request and get the redirect target if possible.
    If not this function returns just `None`.  The return value of this
    function is suitable to be passed to `redirect`.
    """
    check_target = user_url or environ.get('HTTP_REFERER')

    # if there is no information in either the form data
    # or the wsgi environment about a jump target we have
    # to use the target url
    if not check_target:
        return

    # otherwise drop the leading slash
    check_target = check_target.lstrip('/')

    root_url = get_current_url(environ)
    root_parts = urlparse(root_url)

    check_parts = urlparse(urljoin(root_url, check_target))
    check_query = urldecode(check_parts[4])

    def url_equals(to_check):
        if to_check[:4] != check_parts[:4]:
            return False
        args = urldecode(to_check[4])
        for key, value in args:
            if check_query.get(key) != value:
                return False
        return True

    allowed_redirects = chain([get_host(environ)], allowed_redirects or ())

    # if the jump target is on a different server we probably have
    # a security problem and better try to use the target url.
    # except the host is whitelisted in the config
    if root_parts[:2] != check_parts[:2]:
        host = check_parts[1].split(':', 1)[0]
        for rule in allowed_redirects:
            if fnmatch(host, rule):
                break
        else:
            return

    # if the jump url is the same url as the current url we've had
    # a bad redirect before and use the target url to not create a
    # infinite redirect.
    if url_equals(urlparse(get_current_url(environ))):
        return

    # if the `check_target` is one of the invalid targets we also
    # fall back.
    for invalid in invalid_targets:
        if url_equals(urlparse(urljoin(root_url, invalid))):
            return

    return check_target
