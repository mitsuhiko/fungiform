# -*- coding: utf-8 -*-
"""
    fungiform.utils
    ~~~~~~~~~~~~~~~

    Various utilities.

    :copyright: (c) 2010 by the Fungiform Team.
    :license: BSD, see LICENSE for more details.
"""
import re
from copy import deepcopy
from itertools import izip, imap
from datetime import datetime, date
from time import strptime

DATE_FORMATS = ['%m/%d/%Y', '%d/%m/%Y', '%Y%m%d', '%d. %m. %Y',
                '%m/%d/%y', '%d/%m/%y', '%d%m%y', '%m%d%y', '%y%m%d']
TIME_FORMATS = ['%H:%M', '%H:%M:%S', '%I:%M %p', '%I:%M:%S %p']
_missing = object()


def get_current_url(environ):
    """A handy helper function that recreates the full URL for the current
    request.

    :param environ: the WSGI environment to get the current URL from.
    """
    tmp = [environ['wsgi.url_scheme'], '://', get_host(environ)]
    cat = tmp.append
    cat(urllib.quote(environ.get('SCRIPT_NAME', '').rstrip('/')))
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


def _force_list(value):
    """If the value is not a list, make it one."""
    if value is None:
        return []
    try:
        if isinstance(value, basestring):
            raise TypeError()
        return list(value)
    except TypeError:
        return [value]


def _to_list(value):
    """Similar to `_force_list` but always succeeds and never drops data."""
    if value is None:
        return []
    if isinstance(value, basestring):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def _force_dict(value):
    """If the value is not a dict, raise an exception."""
    if value is None or not isinstance(value, dict):
        return {}
    return value


def _to_string(value):
    """Convert a value to unicode, None means empty string."""
    if value is None:
        return u''
    return unicode(value)


def _value_matches_choice(value, choice):
    """Checks if a given value matches a choice."""
    # this algorithm is also implemented in `MultiChoiceField.convert`
    # for better scaling with multiple items.  If it's changed here, it
    # must be changed for the multi choice field too.
    return choice == value or _to_string(choice) == _to_string(value)


def _make_widget(field, name, value, errors):
    """Shortcut for widget creation."""
    return field.widget(field, name, value, errors)


def soft_unicode(s):
    """Make something unicode if it's not a string or respond to `__html__`"""
    if hasattr(s, '__html__'):
        return s
    elif not isinstance(s, basestring):
        return unicode(s)
    return s


def escape(s):
    """Replace special characters "&", '"', "<" and ">" to HTML-safe sequences.

    There is a special handling for `None` which escapes to an empty string.

    :param s: the string to escape.
    :param quote: set to true to also escape double quotes.
    """
    if s is None:
        return ''
    elif hasattr(s, '__html__'):
        return s.__html__()
    elif not isinstance(s, basestring):
        s = unicode(s)
    return Markup(s.replace(u'&', u'&amp;').replace(u'<', u'&lt;')
                   .replace(u'>', u'&gt;').replace(u'"', u'&#34;'))


def make_name(parent, child):
    """Joins a name."""
    if parent is None:
        result = child
    else:
        result = '%s.%s' % (parent, child)

    # try to return a ascii only bytestring if possible
    try:
        return str(result)
    except UnicodeError:
        return unicode(result)


def fill_dict(_dict, **kwargs):
    """A helper to fill the dict passed with the items passed as keyword
    arguments if they are not yet in the dict.  If the dict passed was
    `None` a new dict is created and returned.

    This can be used to prepopulate initial dicts in overriden constructors:

        class MyForm(forms.Form):
            foo = forms.TextField()
            bar = forms.TextField()

            def __init__(self, initial=None):
                forms.Form.__init__(self, forms.fill_dict(initial,
                    foo="nothing",
                    bar="nothing"
                ))
    """
    if _dict is None:
        return kwargs
    for key, value in kwargs.iteritems():
        if key not in _dict:
            _dict[key] = value
    return _dict


def set_fields(obj, data, *fields):
    """Set all the fields on obj with data if changed."""
    for field in fields:
        value = data[field]
        if getattr(obj, field) != value:
            setattr(obj, field, value)


def _iter_key_grouped(iterable):
    """A helper that groups an ``(key, value)`` iterable by key and
    accumultates the values in a list.  Used to support webob like dicts in
    the form data decoder.
    """
    last_key = None
    buffered = []
    for key, value in sorted(iterable, key=lambda x: x[0]):
        if key != last_key and buffered:
            yield last_key, buffered
            buffered = []
        last_key = key
        buffered.append(value)
    if buffered:
        yield last_key, buffered


def decode_form_data(data):
    """Decodes the flat dictionary d into a nested structure.

    >>> decode_form_data({'foo': 'bar'})
    {'foo': 'bar'}
    >>> decode_form_data({'foo.0': 'bar', 'foo.1': 'baz'})
    {'foo': ['bar', 'baz']}
    >>> data = decode_form_data({'foo.bar': '1', 'foo.baz': '2'})
    >>> data == {'foo': {'bar': '1', 'baz': '2'}}
    True

    More complex mappings work too:

    >>> decode_form_data({'foo.bar.0': 'baz', 'foo.bar.1': 'buzz'})
    {'foo': {'bar': ['baz', 'buzz']}}
    >>> decode_form_data({'foo.0.bar': '23', 'foo.1.baz': '42'})
    {'foo': [{'bar': '23'}, {'baz': '42'}]}
    >>> decode_form_data({'foo.0.0': '23', 'foo.0.1': '42'})
    {'foo': [['23', '42']]}
    >>> decode_form_data({'foo': ['23', '42']})
    {'foo': ['23', '42']}

    _missing items in lists are ignored for convenience reasons:

    >>> decode_form_data({'foo.42': 'a', 'foo.82': 'b'})
    {'foo': ['a', 'b']}

    This can be used for help client side DOM processing (inserting and
    deleting rows in dynamic forms).

    It also supports werkzeug's and django's multi dicts (or a dict like
    object that provides an `iterlists`):

    >>> class MultiDict(dict):
    ...     def iterlists(self):
    ...         for key, values in dict.iteritems(self):
    ...             yield key, list(values)
    >>> decode_form_data(MultiDict({"foo": ['1', '2']}))
    {'foo': ['1', '2']}
    >>> decode_form_data(MultiDict({"foo.0": '1', "foo.1": '2'}))
    {'foo': ['1', '2']}

    Those two submission ways can also be used combined:

    >>> decode_form_data(MultiDict({"foo": ['1'], "foo.0": '2', "foo.1": '3'}))
    {'foo': ['1', '2', '3']}

    This function will never raise exceptions except for argument errors
    but the recovery behavior for invalid form data is undefined.
    """
    list_marker = object()
    value_marker = object()

    if hasattr(data, 'iterlists'):
        listiter = data.iterlists()
    else:
        if type(data) is dict:
            listiter = data.iteritems()
        else:
            listiter = _iter_key_grouped(data.items())
        listiter = ((k, not isinstance(v, (list, tuple)) and [v] or v)
                    for k, v in listiter)

    def _split_key(name):
        result = name.split('.')
        for idx, part in enumerate(result):
            if part.isdigit():
                result[idx] = int(part)
        return result

    def _enter_container(container, key):
        if key not in container:
            return container.setdefault(key, {list_marker: False})
        return container[key]

    def _convert(container):
        if value_marker in container:
            force_list = False
            values = container.pop(value_marker)
            if container.pop(list_marker):
                force_list = True
                values.extend(_convert(x[1]) for x in
                              sorted(container.items()))
            if not force_list and len(values) == 1:
                values = values[0]
            return values
        elif container.pop(list_marker):
            return [_convert(x[1]) for x in sorted(container.items())]
        return dict((k, _convert(v)) for k, v in container.iteritems())

    result = {list_marker: False}
    for key, values in listiter:
        parts = _split_key(key)
        if not parts:
            continue
        container = result
        for part in parts:
            last_container = container
            container = _enter_container(container, part)
            last_container[list_marker] = isinstance(part, (int, long))
        container[value_marker] = values

    return _convert(result)


class Markup(unicode):
    r"""Marks a string as being safe for inclusion in HTML/XML output without
    needing to be escaped.  This implements the `__html__` interface a couple
    of frameworks and web applications use.  :class:`Markup` is a direct
    subclass of `unicode` and provides all the methods of `unicode` just that
    it escapes arguments passed and always returns `Markup`.

    The constructor of the :class:`Markup` class can be used for three
    different things:  When passed an unicode object it's assumed to be safe,
    when passed an object with an HTML representation (has an `__html__`
    method) that representation is used, otherwise the object passed is
    converted into a unicode string and then assumed to be safe:

    >>> Markup("Hello <em>World</em>!")
    u'Hello <em>World</em>!'
    >>> class Foo(object):
    ...  def __html__(self):
    ...   return '<a href="#">foo</a>'
    ...
    >>> Markup(Foo())
    u'<a href="#">foo</a>'

    """
    __slots__ = ()

    def __new__(cls, base=u'', encoding=None, errors='strict'):
        if hasattr(base, '__html__'):
            base = base.__html__()
        if encoding is None:
            return unicode.__new__(cls, base)
        return unicode.__new__(cls, base, encoding, errors)

    def __html__(self):
        return self

    def __add__(self, other):
        if hasattr(other, '__html__') or isinstance(other, basestring):
            return self.__class__(unicode(self) + unicode(escape(other)))
        return NotImplemented

    def __radd__(self, other):
        if hasattr(other, '__html__') or isinstance(other, basestring):
            return self.__class__(unicode(escape(other)) + unicode(self))
        return NotImplemented

    def __mul__(self, num):
        if isinstance(num, (int, long)):
            return self.__class__(unicode.__mul__(self, num))
        return NotImplemented
    __rmul__ = __mul__

    def __mod__(self, arg):
        if isinstance(arg, tuple):
            arg = tuple(imap(_MarkupEscapeHelper, arg))
        else:
            arg = _MarkupEscapeHelper(arg)
        return self.__class__(unicode.__mod__(self, arg))

    def join(self, seq):
        return self.__class__(unicode.join(self, imap(escape, seq)))
    join.__doc__ = unicode.join.__doc__

    def split(self, *args, **kwargs):
        return map(self.__class__, unicode.split(self, *args, **kwargs))
    split.__doc__ = unicode.split.__doc__

    def rsplit(self, *args, **kwargs):
        return map(self.__class__, unicode.rsplit(self, *args, **kwargs))
    rsplit.__doc__ = unicode.rsplit.__doc__

    def splitlines(self, *args, **kwargs):
        return map(self.__class__, unicode.splitlines(self, *args, **kwargs))
    splitlines.__doc__ = unicode.splitlines.__doc__

    def make_wrapper(name):
        orig = getattr(unicode, name)

        def func(self, *args, **kwargs):
            args = _escape_argspec(list(args), enumerate(args))
            _escape_argspec(kwargs, kwargs.iteritems())
            return self.__class__(orig(self, *args, **kwargs))
        func.__name__ = orig.__name__
        func.__doc__ = orig.__doc__
        return func

    for method in '__getitem__', 'capitalize', \
                  'title', 'lower', 'upper', 'replace', 'ljust', \
                  'rjust', 'lstrip', 'rstrip', 'center', 'strip', \
                  'translate', 'expandtabs', 'swapcase', 'zfill':
        locals()[method] = make_wrapper(method)

    # new in python 2.5
    if hasattr(unicode, 'partition'):
        partition = make_wrapper('partition'),
        rpartition = make_wrapper('rpartition')

    # new in python 2.6
    if hasattr(unicode, 'format'):
        format = make_wrapper('format')

    del method, make_wrapper


def _escape_argspec(obj, iterable):
    """Helper for various string-wrapped functions."""
    for key, value in iterable:
        if hasattr(value, '__html__') or isinstance(value, basestring):
            obj[key] = escape(value)
    return obj


class _MarkupEscapeHelper(object):
    """Helper for Markup.__mod__"""

    def __init__(self, obj):
        self.obj = obj

    __getitem__ = lambda s, x: _MarkupEscapeHelper(s.obj[x])
    __str__ = lambda s: str(escape(s.obj))
    __unicode__ = lambda s: unicode(escape(s.obj))
    __repr__ = lambda s: str(escape(repr(s.obj)))
    __int__ = lambda s: int(s.obj)
    __float__ = lambda s: float(s.obj)


class HTMLBuilder(object):
    """Helper object for HTML generation.

    Per default there are two instances of that class.  The `html` one, and
    the `xhtml` one for those two dialects.  The class uses keyword parameters
    and positional parameters to generate small snippets of HTML.

    Keyword parameters are converted to XML/SGML attributes, positional
    arguments are used as children.  Because Python accepts positional
    arguments before keyword arguments it's a good idea to use a list with the
    star-syntax for some children:

    >>> html.p(class_='foo', *[html.a('foo', href='foo.html'), ' ',
    ...                        html.a('bar', href='bar.html')])
    u'<p class="foo"><a href="foo.html">foo</a> <a href="bar.html">bar</a></p>'

    This class works around some browser limitations and can not be used for
    arbitrary SGML/XML generation.  For that purpose lxml and similar
    libraries exist.

    Calling the builder escapes the string passed:

    >>> html.p(html("<foo>"))
    u'<p>&lt;foo&gt;</p>'
    """
    # this class is taken from werkzeug.utils.  Please modify both in werkzeug
    # and copy over here if you fix bugs.

    from htmlentitydefs import name2codepoint
    _entity_re = re.compile(r'&([^;]+);')
    _entities = name2codepoint.copy()
    _entities['apos'] = 39
    _empty_elements = set([
        'area', 'base', 'basefont', 'br', 'col', 'frame', 'hr', 'img',
        'input', 'isindex', 'link', 'meta', 'param'
    ])
    _boolean_attributes = set([
        'selected', 'checked', 'compact', 'declare', 'defer', 'disabled',
        'ismap', 'multiple', 'nohref', 'noresize', 'noshade', 'nowrap'
    ])
    _plaintext_elements = set(['textarea'])
    _c_like_cdata = set(['script', 'style'])
    del name2codepoint

    def __init__(self, dialect):
        self._dialect = dialect

    def __call__(self, s):
        return escape(s)

    def __getattr__(self, tag):
        if tag[:2] == '__':
            raise AttributeError(tag)

        def proxy(*children, **arguments):
            buffer = ['<' + tag]
            write = buffer.append
            for key, value in arguments.iteritems():
                if value is None:
                    continue
                if key.endswith('_'):
                    key = key[:-1]
                if key in self._boolean_attributes:
                    if not value:
                        continue
                    value = self._dialect == 'xhtml' and '="%s"' % key or ''
                else:
                    value = '="%s"' % escape(value)
                write(' ' + key + value)
            if not children and tag in self._empty_elements:
                write(self._dialect == 'xhtml' and ' />' or '>')
                return Markup(u''.join(buffer))
            write('>')
            if tag in self._c_like_cdata:
                children_as_string = u''.join(unicode(x) for x in children
                                              if x is not None)
                if self._dialect == 'xhtml':
                    children_as_string = \
                        '/*<![CDATA[*/%s/*]]>*/' % children_as_string
            else:
                children_as_string = Markup(u''.join(
                    escape(x) for x in children if x is not None))
            buffer.extend((children_as_string, '</%s>' % tag))
            return Markup(u''.join(buffer))
        return proxy

    def __repr__(self):
        return '<%s for %r>' % (
            self.__class__.__name__,
            self._dialect
        )


html = HTMLBuilder('html')
xhtml = HTMLBuilder('xhtml')


class OrderedDict(dict):
    """Simple ordered dict implementation.

    It's a dict subclass and provides some list functions.  The implementation
    of this class is inspired by the implementation of Babel but incorporates
    some ideas from the `ordereddict`_ and Django's ordered dict.

    The constructor and `update()` both accept iterables of tuples as well as
    mappings:

    >>> d = OrderedDict([('a', 'b'), ('c', 'd')])
    >>> d.update({'foo': 'bar'})
    >>> d
    OrderedDict([('a', 'b'), ('c', 'd'), ('foo', 'bar')])

    Keep in mind that when updating from dict-literals the order is not
    preserved as these dicts are unsorted!

    You can copy an OrderedDict like a dict by using the constructor,
    `copy.copy` or the `copy` method and make deep copies with `copy.deepcopy`:

    >>> from copy import copy, deepcopy
    >>> copy(d)
    OrderedDict([('a', 'b'), ('c', 'd'), ('foo', 'bar')])
    >>> d.copy()
    OrderedDict([('a', 'b'), ('c', 'd'), ('foo', 'bar')])
    >>> OrderedDict(d)
    OrderedDict([('a', 'b'), ('c', 'd'), ('foo', 'bar')])
    >>> d['spam'] = []
    >>> d2 = deepcopy(d)
    >>> d2['spam'].append('eggs')
    >>> d
    OrderedDict([('a', 'b'), ('c', 'd'), ('foo', 'bar'), ('spam', [])])
    >>> d2
    OrderedDict([('a', 'b'), ('c', 'd'), ('foo', 'bar'), ('spam', ['eggs'])])

    All iteration methods as well as `keys`, `values` and `items` return
    the values ordered by the the time the key-value pair is inserted:

    >>> d.keys()
    ['a', 'c', 'foo', 'spam']
    >>> d.values()
    ['b', 'd', 'bar', []]
    >>> d.items()
    [('a', 'b'), ('c', 'd'), ('foo', 'bar'), ('spam', [])]
    >>> list(d.iterkeys())
    ['a', 'c', 'foo', 'spam']
    >>> list(d.itervalues())
    ['b', 'd', 'bar', []]
    >>> list(d.iteritems())
    [('a', 'b'), ('c', 'd'), ('foo', 'bar'), ('spam', [])]

    Index based lookup is supported too by `byindex` which returns the
    key/value pair for an index:

    >>> d.byindex(2)
    ('foo', 'bar')

    You can reverse the OrderedDict as well:

    >>> d.reverse()
    >>> d
    OrderedDict([('spam', []), ('foo', 'bar'), ('c', 'd'), ('a', 'b')])

    And sort it like a list:

    >>> d.sort(key=lambda x: x[0].lower())
    >>> d
    OrderedDict([('a', 'b'), ('c', 'd'), ('foo', 'bar'), ('spam', [])])

    For performance reasons the ordering is not taken into account when
    comparing two ordered dicts.

    .. _ordereddict: http://www.xs4all.nl/~anthon/Python/ordereddict/
    """

    def __init__(self, *args, **kwargs):
        dict.__init__(self)
        self._keys = []
        self.update(*args, **kwargs)

    def __delitem__(self, key):
        dict.__delitem__(self, key)
        self._keys.remove(key)

    def __setitem__(self, key, item):
        if key not in self:
            self._keys.append(key)
        dict.__setitem__(self, key, item)

    def __deepcopy__(self, memo):
        d = memo.get(id(self), _missing)
        memo[id(self)] = d = self.__class__()
        dict.__init__(d, deepcopy(self.items(), memo))
        d._keys = self._keys[:]
        return d

    def __reduce__(self):
        return type(self), self.items()

    def __reversed__(self):
        return reversed(self._keys)

    @classmethod
    def fromkeys(cls, iterable, default=None):
        return cls((key, default) for key in iterable)

    def clear(self):
        del self._keys[:]
        dict.clear(self)

    def move(self, key, index):
        self._keys.remove(key)
        self._keys.insert(index, key)

    def copy(self):
        return self.__class__(self)

    def items(self):
        return zip(self._keys, self.values())

    def iteritems(self):
        return izip(self._keys, self.itervalues())

    def keys(self):
        return self._keys[:]

    def iterkeys(self):
        return iter(self._keys)

    def pop(self, key, default=_missing):
        if default is _missing:
            return dict.pop(self, key)
        elif key not in self:
            return default
        self._keys.remove(key)
        return dict.pop(self, key, default)

    def popitem(self, key):
        self._keys.remove(key)
        return dict.popitem(self, key)

    def setdefault(self, key, default=None):
        if key not in self:
            self._keys.append(key)
        dict.setdefault(self, key, default)

    def update(self, *args, **kwargs):
        sources = []
        if len(args) == 1:
            if hasattr(args[0], 'iteritems'):
                sources.append(args[0].iteritems())
            else:
                sources.append(iter(args[0]))
        elif args:
            raise TypeError('expected at most one positional argument')
        if kwargs:
            sources.append(kwargs.iteritems())
        for iterable in sources:
            for key, val in iterable:
                self[key] = val

    def values(self):
        return map(self.get, self._keys)

    def itervalues(self):
        return imap(self.get, self._keys)

    def index(self, item):
        return self._keys.index(item)

    def byindex(self, item):
        key = self._keys[item]
        return (key, dict.__getitem__(self, key))

    def reverse(self):
        self._keys.reverse()

    def sort(self, cmp=None, key=None, reverse=False):
        if key is not None:
            self._keys.sort(key=lambda k: key((k, self[k])))
        elif cmp is not None:
            self._keys.sort(lambda a, b: cmp((a, self[a]), (b, self[b])))
        else:
            self._keys.sort()
        if reverse:
            self._keys.reverse()

    def __repr__(self):
        return '%s(%r)' % (type(self).__name__, self.items())

    __copy__ = copy
    __iter__ = iterkeys


# Date and Time

try:
    from pytz import timezone, UTC
except ImportError, exc:

    # Naive functions, if the pytz module cannot be imported.

    def to_utc(datetime, tzinfo=None):
        if tzinfo is None:
            return datetime
        raise exc
    to_timezone = to_utc

    def get_timezone(name=None):
        if name is None:
            return None
        raise exc

else:

    def to_utc(datetime, tzinfo=UTC):
        """Convert a datetime object to UTC and drop tzinfo."""
        if datetime.tzinfo is None:
            datetime = tzinfo.localize(datetime)
        return datetime.astimezone(UTC).replace(tzinfo=None)

    def to_timezone(datetime, tzinfo=UTC):
        """Convert a datetime object to the local timezone."""
        if datetime.tzinfo is None:
            datetime = datetime.replace(tzinfo=UTC)
        return tzinfo.normalize(datetime.astimezone(tzinfo))

    def get_timezone(name=None):
        """Return the timezone for the given identifier or the timezone
        of the application based on the configuration.
        """
        if name is None:
            return UTC
        return timezone(name)


def format_system_datetime(datetime=None, tzinfo=None):
    """Formats a system datetime.

    (Format: YYYY-MM-DD hh:mm and in the user timezone
    if tzinfo is provided)
    """
    if tzinfo:
        datetime = to_timezone(datetime, tzinfo)
    return u'%d-%02d-%02d %02d:%02d' % (
        datetime.year,
        datetime.month,
        datetime.day,
        datetime.hour,
        datetime.minute
    )


def format_system_date(date=None):
    """Formats a system date.

    (Format: YYYY-MM-DD)
    """
    return u'%d-%02d-%02d' % (date.year, date.month, date.day)


def parse_datetime(string, tzinfo=None):
    """Parses a string into a datetime object.  Per default a conversion
    from the local timezone to UTC is performed but returned as naive
    datetime object (that is tzinfo being None).  If tzinfo is not used,
    the string is expected in UTC.

    The return value is **always** a naive datetime object in UTC.  This
    function should be considered of a lenient counterpart of
    `format_system_datetime`.
    """
    # shortcut: string as None or "now" returns the current timestamp.
    if string is None or string.lower() in ('now',):
        return datetime.utcnow().replace(microsecond=0)

    def convert(format):
        """Helper that parses the string and convers the timezone."""
        rv = datetime(*strptime(string, format)[:7])
        if tzinfo:
            rv = to_utc(rv, tzinfo)
        return rv.replace(microsecond=0)

    # first of all try the following format because this is the format
    # Texpress will output by default for any date time string in the
    # administration panel.
    try:
        return convert(u'%Y-%m-%d %H:%M')
    except ValueError:
        pass

    # no go with time only, and current day
    for fmt in TIME_FORMATS:
        try:
            val = convert(fmt)
        except ValueError:
            continue
        return to_utc(datetime.utcnow().replace(hour=val.hour,
                      minute=val.minute, second=val.second, microsecond=0),
                      tzinfo=tzinfo)

    # now try various types of date + time strings
    def combined():
        for t_fmt in TIME_FORMATS:
            for d_fmt in DATE_FORMATS:
                yield t_fmt + ' ' + d_fmt
                yield d_fmt + ' ' + t_fmt

    for fmt in combined():
        try:
            return convert(fmt)
        except ValueError:
            pass

    raise ValueError('invalid date format')


def parse_date(string):
    """Parses a string into a date object."""
    # shortcut: string as None or "today" returns the current date.
    if string is None or string.lower() in ('today',):
        return date.today()

    def convert(format):
        """Helper that parses the string."""
        return date(*strptime(string, format)[:3])

    # first of all try the ISO 8601 format.
    try:
        return convert(u'%Y-%m-%d')
    except ValueError:
        pass

    # now try various types of date
    for fmt in DATE_FORMATS:
        try:
            return convert(fmt)
        except ValueError:
            pass

    raise ValueError('invalid date format')
