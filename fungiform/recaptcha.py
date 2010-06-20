# -*- coding: utf-8 -*-
"""
    fungiform.recaptcha
    ~~~~~~~~~~~~~~~~~~~

    Recaptcha support.

    :copyright: (c) 2010 by the Fungiform Team.
    :license: BSD, see LICENSE for more details.
"""
from fungiform.utils import Markup
from urllib import urlencode
import urllib2
try:
    from simplejson import dumps
except ImportError:
    try:
        from json import dumps
    except ImportError:

        def dumps(x):
            raise RuntimeError('for captcha support, simplejson has to '
                               'be installed.')


API_SERVER = 'http://api.recaptcha.net/'
SSL_API_SERVER = 'https://api-secure.recaptcha.net/'
VERIFY_SERVER = 'http://api-verify.recaptcha.net/verify'


def get_recaptcha_html(public_key=None, use_ssl=True, error=None,
                       translations=None):
    """Returns the recaptcha input HTML."""
    _ = translations and translations.ugettext or (lambda x: x)
    server = use_ssl and API_SERVER or SSL_API_SERVER
    options = dict(k=public_key.encode('utf-8'))
    if error is not None:
        options['error'] = unicode(error).encode('utf-8')
    query = urlencode(options)
    return Markup(u'''
    <script type="text/javascript">var RecaptchaOptions = %(options)s;</script>
    <script type="text/javascript" src="%(script_url)s"></script>
    <noscript>
      <div><iframe src="%(frame_url)s" height="300" width="500"></iframe></div>
      <div><textarea name="recaptcha_challenge_field"
                     rows="3" cols="40"></textarea>
      <input type="hidden" name="recaptcha_response_field"
             value="manual_challenge"></div>
    </noscript>
    ''' % dict(
        script_url='%schallenge?%s' % (server, query),
        frame_url='%snoscript?%s' % (server, query),
        options=dumps({
            'theme':    'clean',
            'custom_translations': {
                'visual_challenge': _("Get a visual challenge"),
                'audio_challenge': _("Get an audio challenge"),
                'refresh_btn': _("Get a new challenge"),
                'instructions_visual': _("Type the two words:"),
                'instructions_audio': _("Type what you hear:"),
                'help_btn': _("Help"),
                'play_again': _("Play sound again"),
                'cant_hear_this': _("Download sound as MP3"),
                'incorrect_try_again': _("Incorrect. Try again.")
            }
        })
    ))


def validate_recaptcha(private_key, challenge, response, remote_ip):
    """Validates the recaptcha.  If the validation fails
    a `RecaptchaValidationFailed` error is raised.
    """
    request = urllib2.Request(VERIFY_SERVER, data=urlencode({
        'privatekey':       private_key.encode('utf-8'),
        'remoteip':         remote_ip.encode('utf-8'),
        'challenge':        challenge.encode('utf-8'),
        'response':         response.encode('utf-8')
    }))
    response = urllib2.urlopen(request)
    rv = response.read().splitlines()
    response.close()
    if rv and rv[0] == 'true':
        return True
    if len(rv) > 1:
        error = rv[1]
        if error == 'invalid-site-public-key':
            raise RuntimeError('invalid public key for recaptcha set')
        if error == 'invalid-site-private-key':
            raise RuntimeError('invalid private key for recaptcha set')
        if error == 'invalid-referrer':
            raise RuntimeError('key not valid for the current domain')
    return False
