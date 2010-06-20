# -*- coding: utf-8 -*-
"""
    fungiform.exceptions
    ~~~~~~~~~~~~~~~~~~~~

    Exception classes.

    :copyright: (c) 2010 by the Fungiform Team.
    :license: BSD, see LICENSE for more details.
"""
from fungiform.utils import make_name
from fungiform.widgets import ErrorList


class ValidationError(ValueError):
    """Exception raised when invalid data is encountered."""

    def __init__(self, message):
        if not isinstance(message, (list, tuple)):
            messages = [message]
        # make all items in the list unicode (this also evaluates
        # lazy translations in there)
        messages = map(unicode, messages)
        Exception.__init__(self, messages[0])
        self.messages = messages
        self._messages = None

    def unpack(self, form, key=None):
        if self._messages is None:
            self._messages = ErrorList(form, self.messages)
        return {key: self._messages}


class MultipleValidationErrors(ValidationError):
    """A validation error subclass for multiple errors raised by
    subfields.  This is used by the mapping and list fields.
    """

    def __init__(self, errors):
        ValidationError.__init__(self, '%d error%s' % (
            len(errors), len(errors) != 1 and 's' or ''
        ))
        self.errors = errors

    def __unicode__(self):
        return ', '.join(map(unicode, self.errors.itervalues()))

    def unpack(self, form, key=None):
        rv = {}
        for name, error in self.errors.iteritems():
            rv.update(error.unpack(form, make_name(key, name)))
        return rv
