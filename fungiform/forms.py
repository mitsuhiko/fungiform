# -*- coding: utf-8 -*-
"""
    fungiform.forms
    ~~~~~~~~~~~~~~~

    This module implements all forms and helpers to implement a proper
    form handling.

    How to use validators
    ---------------------

    Validators are just simple functions with two arguments, the actual form
    and the value to validate.  A simple validator could look like this::

        def is_valid_email(form, value):
            if '@' not in value or len(value) > 200:
                raise ValidationError('Invalid email address')

    Now just apply these validators to the form field::

        class MyForm(FormBase):
            name = TextField(u'Name: ', required=True)
            email = TextField(u'Email: ', validators=[is_valid_email])


    :copyright: (c) 2010 by the Fungiform Team.
    :license: BSD, see LICENSE for more details.
"""
from datetime import datetime, date
from itertools import count
from threading import Lock
from urlparse import urljoin

from fungiform import widgets
from fungiform.exceptions import ValidationError, MultipleValidationErrors
from fungiform.utils import OrderedDict, decode_form_data, \
                            format_system_datetime, format_system_date, \
                            parse_datetime, parse_date, get_timezone, \
                            _force_dict, _force_list, _to_string, _to_list, \
                            html, _make_widget, _value_matches_choice, \
                            get_current_url
from fungiform.recaptcha import validate_recaptcha
from fungiform.redirects import get_redirect_target
from fungiform.csrf import get_csrf_token, invalidate_csrf_token


__all__ = ['FormBase', 'Field', 'Mapping', 'Multiple', 'CommaSeparated',
           'LineSeparated', 'TextField', 'PasswordField', 'DateTimeField',
           'DateField', 'ChoiceField', 'MultiChoiceField', 'IntegerField',
           'BooleanField', 'FormBase']


_last_position_hint = -1
_position_hint_lock = Lock()

_next_position_hint = count().next

_dummy_translations = (type('_dummy_translations', (object,), {
    'ugettext':     lambda x, s: s,
    'ungettext':    lambda x, s, p, n: [s, p][n != 1]
}))()


def _bind(obj, form, memo):
    """Helper for the field binding.  This is inspired by the way `deepcopy`
    is implemented.
    """
    if memo is None:
        memo = {}
    obj_id = id(obj)
    if obj_id in memo:
        return memo[obj_id]
    rv = obj._bind(form, memo)
    memo[obj_id] = rv
    return rv


class FieldMeta(type):

    def __new__(cls, name, bases, d):
        messages = {}
        for base in reversed(bases):
            if hasattr(base, 'messages'):
                messages.update(base.messages)
        if 'messages' in d:
            messages.update(d['messages'])
        d['messages'] = messages
        return type.__new__(cls, name, bases, d)


class Field(object):
    """Abstract field base class."""

    __metaclass__ = FieldMeta
    messages = dict(required=None)
    form = None
    widget = widgets.TextInput

    # these attributes are used by the widgets to get an idea what
    # choices to display.  Not every field will also validate them.
    multiple_choices = False
    choices = ()

    # fields that have this attribute set get special treatment on
    # validation.  It means that even though a value was not in the
    # submitted data it's validated against a default value.
    validate_on_omission = False

    def __init__(self, label=None, help_text=None, validators=None,
                 widget=None, messages=None, sentinel=False):
        self._position_hint = _next_position_hint()
        self.label = label
        self.help_text = help_text
        if validators is None:
            validators = []
        self.validators = validators
        self.custom_converter = None
        if widget is not None:
            self.widget = widget
        if messages:
            self.messages = self.messages.copy()
            self.messages.update(messages)
        self.sentinel = sentinel
        assert not issubclass(self.widget, widgets.InternalWidget), \
            'can\'t use internal widgets as widgets for fields'

    def gettext(self, string):
        if self.form is None:
            return string
        return self.form._get_translations().ugettext(string)

    def ngettext(self, sg, pl, n):
        if self.form is None:
            return [sg, pl](n != 1)
        return self.form._get_translations().ungettext(sg, pl, n)

    def __call__(self, value):
        value = self.convert(value)
        self.apply_validators(value)
        return value

    def __copy__(self):
        return _bind(self, None, None)

    def apply_validators(self, value):
        """Applies all validators on the value."""
        if self.should_validate(value):
            for validate in self.validators:
                validate(self.form, value)

    def empty_as_item(self, value):
        """Multiple fields use this method to decide if the field is
        considered empty or not.  Empty fields are not validated and
        stored.  For this function to ever return `True` it has to be
        defined as sentinel.  Example::

            items = Multiple(Mapping(
                name = TextField(required=True),
                count = IntegerField(required=True, sentinel=True)
            ))

        If the count is omitted the item will not be validated and
        added to the list.  As soon as a value is inserted to the
        count field, validation happens.
        """
        return self.sentinel and not value

    def should_validate(self, value):
        """Per default validate if the value is not None.  This method is
        called before the custom validators are applied to not perform
        validation if the field is empty and not required.

        For example a validator like `is_valid_ip` is never called if the
        value is an empty string and the field hasn't raised a validation
        error when checking if the field is required.
        """
        return value is not None

    def convert(self, value):
        """This can be overridden by subclasses and performs the value
        conversion.
        """
        return _to_string(value)

    def to_primitive(self, value):
        """Convert a value into a primitve (string or a list/dict of lists,
        dicts or strings).

        This method must never fail!
        """
        return _to_string(value)

    def _bind(self, form, memo):
        """Method that binds a field to a form. If `form` is None, a copy of
        the field is returned."""
        if form is not None and self.bound:
            raise TypeError('%r already bound' % type(obj).__name__)
        rv = object.__new__(self.__class__)
        rv.__dict__.update(self.__dict__)
        rv.validators = self.validators[:]
        rv.messages = self.messages.copy()
        if form is not None:
            rv.form = form
        return rv

    @property
    def bound(self):
        """True if the form is bound."""
        return 'form' in self.__dict__

    def __repr__(self):
        rv = object.__repr__(self)
        if self.bound:
            rv = rv[:-1] + ' [bound]>'
        return rv


class Mapping(Field):
    """Apply a set of fields to a dictionary of values.

    >>> field = Mapping(name=TextField(), age=IntegerField())
    >>> field({'name': u'John Doe', 'age': u'42'})
    {'age': 42, 'name': u'John Doe'}

    Although it's possible to reassign the widget after field construction
    it's not recommended because the `MappingWidget` is the only builtin
    widget that is able to handle mapping structures.
    """

    widget = widgets.MappingWidget

    def __init__(self, *args, **fields):
        Field.__init__(self)
        if len(args) == 1:
            if fields:
                raise TypeError('keyword arguments and dict given')
            self.fields = OrderedDict(args[0])
        else:
            if args:
                raise TypeError('no positional arguments allowed if keyword '
                                'arguments provided.')
            self.fields = OrderedDict(fields)
        self.fields.sort(key=lambda i: i[1]._position_hint)

    def empty_as_item(self, values):
        for name, field in self.fields.iteritems():
            if field.empty_as_item(values.get(name)):
                return True
        return False

    def convert(self, value):
        value = _force_dict(value)
        errors = {}
        result = {}
        for name, field in self.fields.iteritems():
            try:
                result[name] = field(value.get(name))
            except ValidationError, e:
                errors[name] = e
        if errors:
            raise MultipleValidationErrors(errors)
        return result

    def to_primitive(self, value):
        value = _force_dict(value)
        result = {}
        for key, field in self.fields.iteritems():
            result[key] = field.to_primitive(value.get(key))
        return result

    def _bind(self, form, memo):
        rv = Field._bind(self, form, memo)
        rv.fields = OrderedDict()
        for key, field in self.fields.iteritems():
            rv.fields[key] = _bind(field, form, memo)
        return rv


class FormMapping(Mapping):
    """Like a mapping but does csrf protection and stuff."""

    widget = widgets.FormWidget

    def convert(self, value):
        if self.form is None:
            raise TypeError('form mapping without form passed is unable '
                            'to convert data')
        if self.form.csrf_protected:
            token = self.form.raw_data.get('_csrf_token')
            if token != self.form.csrf_token:
                message = self.gettext(u'Form submitted multiple times or '
                                       u'session expired.  Try again.')
                raise ValidationError(message)
        if self.form.captcha_protected:
            if not validate_recaptcha(
                    self.form.recaptcha_private_key,
                    self.form.raw_data.get('recaptcha_challenge_field'),
                    self.form.raw_data.get('recaptcha_response_field'),
                    self.form._get_remote_addr()):
                message = self.gettext('You entered an invalid captcha.')
                raise ValidationError(message)
        return Mapping.convert(self, value)


class FormAsField(Mapping):
    """If a form is converted into a field the returned field object is an
    instance of this class.  The behavior is mostly equivalent to a normal
    :class:`Mapping` field with the difference that it as an attribute called
    :attr:`form_class` that points to the form class it was created from.
    """

    def __init__(self):
        raise TypeError('can\'t create %r instances' %
                        self.__class__.__name__)


class Multiple(Field):
    """Apply a single field to a sequence of values.

    >>> field = Multiple(IntegerField())
    >>> field([u'1', u'2', u'3'])
    [1, 2, 3]

    Recommended widgets:

    -   `ListWidget` -- the default one and useful if multiple complex
        fields are in use.
    -   `CheckboxGroup` -- useful in combination with choices
    -   `SelectBoxWidget` -- useful in combination with choices
    """

    widget = widgets.ListWidget
    messages = dict(too_small=None, too_big=None)
    validate_on_omission = True

    def __init__(self, field, label=None, help_text=None, min_size=None,
                 max_size=None, validators=None, widget=None, messages=None):
        Field.__init__(self, label, help_text, validators, widget, messages)
        self.field = field
        self.min_size = min_size
        self.max_size = max_size

    @property
    def multiple_choices(self):
        return self.max_size is None or self.max_size > 1

    def empty_as_item(self, values):
        for idx, value in enumerate(values):
            if self.field.empty_as_item(value):
                return True
        return False

    def _remove_empty(self, values):
        return [(idx, value) for idx, value in enumerate(values)
                if not self.field.empty_as_item(value)]

    def convert(self, value):
        value = self._remove_empty(_force_list(value))
        if self.min_size is not None and len(value) < self.min_size:
            message = self.messages['too_small']
            if message is None:
                message = self.ngettext(
                    u'Please provide at least %d item.',
                    u'Please provide at least %d items.',
                    self.min_size) % self.min_size
            raise ValidationError(message)
        if self.max_size is not None and len(value) > self.max_size:
            message = self.messages['too_big']
            if message is None:
                message = self.ngettext(
                    u'Please provide no more than %d item.',
                    u'Please provide no more than %d items.',
                    self.max_size) % self.max_size
            raise ValidationError(message)
        result = []
        errors = {}
        for idx, item in value:
            try:
                result.append(self.field(item))
            except ValidationError, e:
                errors[idx] = e
        if errors:
            raise MultipleValidationErrors(errors)
        return result

    def to_primitive(self, value):
        return map(self.field.to_primitive, _force_list(value))

    def _bind(self, form, memo):
        rv = Field._bind(self, form, memo)
        rv.field = _bind(self.field, form, memo)
        return rv


class CommaSeparated(Multiple):
    """Works like the multiple field but for comma separated values:

    >>> field = CommaSeparated(IntegerField())
    >>> field(u'1, 2, 3')
    [1, 2, 3]

    The default widget is a `TextInput` but `Textarea` would be a possible
    choices as well.
    """

    widget = widgets.TextInput

    def __init__(self, field, label=None, help_text=None, min_size=None,
                 max_size=None, sep=u',', validators=None, widget=None,
                 messages=None):
        Multiple.__init__(self, field, label, help_text, min_size,
                          max_size, validators, widget, messages)
        self.sep = sep

    def convert(self, value):
        if isinstance(value, basestring):
            value = filter(None, [x.strip() for x in value.split(self.sep)])
        return Multiple.convert(self, value)

    def to_primitive(self, value):
        if value is None:
            return u''
        if isinstance(value, basestring):
            return value
        return (self.sep + u' ').join(map(self.field.to_primitive, value))


class LineSeparated(Multiple):
    r"""Works like `CommaSeparated` but uses multiple lines:

    >>> field = LineSeparated(IntegerField())
    >>> field(u'1\n2\n3')
    [1, 2, 3]

    The default widget is a `Textarea` and taht is pretty much the only thing
    that makes sense for this widget.
    """
    widget = widgets.Textarea

    def convert(self, value):
        if isinstance(value, basestring):
            value = filter(None, [x.strip() for x in value.splitlines()])
        return Multiple.convert(self, value)

    def to_primitive(self, value):
        if value is None:
            return u''
        if isinstance(value, basestring):
            return value
        return u'\n'.join(map(self.field.to_primitive, value))


class TextField(Field):
    """Field for strings.

    >>> field = TextField(required=True, min_length=6)
    >>> field('foo bar')
    u'foo bar'
    >>> field('')
    Traceback (most recent call last):
      ...
    ValidationError: This field is required.
    """

    messages = dict(too_short=None, too_long=None)

    def __init__(self, label=None, help_text=None, required=False,
                 min_length=None, max_length=None, validators=None,
                 widget=None, messages=None, sentinel=False):
        Field.__init__(self, label, help_text, validators, widget, messages,
                       sentinel)
        self.required = required
        self.min_length = min_length
        self.max_length = max_length

    def convert(self, value):
        value = _to_string(value)
        if self.required:
            if not value:
                message = self.messages['required']
                if message is None:
                    message = self.gettext(u'This field is required.')
                raise ValidationError(message)
        elif value:
            if self.min_length is not None and len(value) < self.min_length:
                message = self.messages['too_short']
                if message is None:
                    message = self.ngettext(
                        u'Please enter at least %d character.',
                        u'Please enter at least %d characters.',
                        self.min_length) % self.min_length
                raise ValidationError(message)
            if self.max_length is not None and len(value) > self.max_length:
                message = self.messages['too_long']
                if message is None:
                    message = self.ngettext(
                        u'Please enter no more than %d character.',
                        u'Please enter no more than %d characters.',
                        self.max_length) % self.max_length
                raise ValidationError(message)
        return value

    def should_validate(self, value):
        """Validate if the string is not empty."""
        return bool(value)


class PasswordField(TextField):
    """A special :class:`TextField` for passwords."""

    widget = widgets.PasswordInput


class DateTimeField(Field):
    """Field for datetime objects.

    >>> field = DateTimeField()
    >>> field('1970-01-12 00:00')
    datetime.datetime(1970, 1, 12, 0, 0)

    >>> field('foo')
    Traceback (most recent call last):
      ...
    ValidationError: Please enter a valid date.
    """

    messages = dict(invalid_date=None)

    def __init__(self, label=None, help_text=None, required=False,
                 tzinfo=None, validators=None, widget=None, messages=None,
                 date_formats=None, time_formats=None):
        Field.__init__(self, label, help_text, validators, widget, messages)
        self.required = required
        self._tzinfo = get_timezone(tzinfo)
        self.date_formats = date_formats
        self.time_formats = time_formats

    @property
    def tzinfo(self):
        tzinfo = self._tzinfo
        return tzinfo() if hasattr(tzinfo, '__call__') else tzinfo

    def convert(self, value):
        if isinstance(value, datetime):
            return value
        value = _to_string(value)
        if not value:
            if self.required:
                raise ValidationError(self.messages['required'])
            return None
        try:
            return parse_datetime(value, tzinfo=self.tzinfo,
                                  date_formats=self.date_formats,
                                  time_formats=self.time_formats)
        except ValueError:
            message = self.messages['invalid_date']
            if message is None:
                message = self.gettext('Please enter a valid date.')
            raise ValidationError(message)

    def to_primitive(self, value):
        if isinstance(value, datetime):
            value = format_system_datetime(value, tzinfo=self.tzinfo)
        return value


class DateField(Field):
    """Field for date objects.

    >>> field = DateField()
    >>> field('1970-01-12')
    datetime.date(1970, 1, 12)

    >>> field('foo')
    Traceback (most recent call last):
      ...
    ValidationError: Please enter a valid date.
    """

    messages = dict(invalid_date=None)

    def __init__(self, label=None, help_text=None, required=False,
                 validators=None, widget=None, messages=None,
                 date_formats=None):
        Field.__init__(self, label, help_text, validators, widget, messages)
        self.required = required
        self.date_formats = date_formats

    def convert(self, value):
        if isinstance(value, date):
            return value
        value = _to_string(value)
        if not value:
            if self.required:
                raise ValidationError(self.messages['required'])
            return None
        try:
            return parse_date(value, date_formats=self.date_formats)
        except ValueError:
            message = self.messages['invalid_date']
            if message is None:
                message = self.gettext('Please enter a valid date.')
            raise ValidationError(message)

    def to_primitive(self, value):
        if isinstance(value, date):
            value = format_system_date(value)
        return value


class ChoiceField(Field):
    """A field that lets a user select one out of many choices.

    A choice field accepts some choices that are valid values for it.
    Values are compared after converting to unicode which means that
    ``1 == "1"``:

    >>> field = ChoiceField(choices=[1, 2, 3])
    >>> field('1')
    1
    >>> field('42')
    Traceback (most recent call last):
      ...
    ValidationError: Please enter a valid choice.

    Two values `a` and `b` are considered equal if either ``a == b`` or
    ``primitive(a) == primitive(b)`` where `primitive` is the primitive
    of the value.  Primitives are created with the following algorithm:

        1.  if the object is `None` the primitive is the empty string
        2.  otherwise the primitive is the string value of the object

    A choice field also accepts lists of tuples as argument where the
    first item is used for comparing and the second for displaying
    (which is used by the `SelectBoxWidget`):

    >>> field = ChoiceField(choices=[(0, 'inactive'), (1, 'active')])
    >>> field('0')
    0

    Because all fields are bound to the form before validation it's
    possible to assign the choices later:

    >>> class MyForm(FormBase):
    ...     status = ChoiceField()
    ...
    >>> form = MyForm()
    >>> form.status.choices = [(0, 'inactive', 1, 'active')]
    >>> form.validate({'status': '0'})
    True
    >>> form.data
    {'status': 0}

    If a choice field is set to "not required" and a `SelectBox` is used
    as widget you have to provide an empty choice or the field cannot be
    left blank.

    >>> field = ChoiceField(required=False, choices=[('', u'Nothing'),
    ...                                              ('1', u'Something')])
    """

    widget = widgets.SelectBox
    messages = dict(invalid_choice=None)

    def __init__(self, label=None, help_text=None, required=True,
                 choices=None, validators=None, widget=None, messages=None,
                 sentinel=False):
        Field.__init__(self, label, help_text, validators, widget, messages,
                       sentinel)
        self.required = required
        self.choices = choices

    def convert(self, value):
        if not value and not self.required:
            return
        if self.choices:
            for choice in self.choices:
                if isinstance(choice, tuple):
                    choice = choice[0]
                if _value_matches_choice(value, choice):
                    return choice
        message = self.messages['invalid_choice']
        if message is None:
            message = self.gettext('Please enter a valid choice.')
        raise ValidationError(message)

    def _bind(self, form, memo):
        rv = Field._bind(self, form, memo)
        if self.choices is not None:
            rv.choices = list(self.choices)
        return rv


class MultiChoiceField(ChoiceField):
    """A field that lets a user select multiple choices."""

    multiple_choices = True
    messages = dict(too_small=None, too_big=None)
    validate_on_omission = True

    def __init__(self, label=None, help_text=None, choices=None,
                 min_size=None, max_size=None, validators=None,
                 widget=None, messages=None, sentinel=False):
        ChoiceField.__init__(self, label, help_text, min_size > 0, choices,
                             validators, widget, messages, sentinel)
        self.min_size = min_size
        self.max_size = max_size

    def convert(self, value):
        result = []
        known_choices = {}
        for choice in self.choices:
            if isinstance(choice, tuple):
                choice = choice[0]
            known_choices[choice] = choice
            known_choices.setdefault(_to_string(choice), choice)

        x = _to_list(value)
        for value in _to_list(value):
            for version in value, _to_string(value):
                if version in known_choices:
                    result.append(known_choices[version])
                    break
            else:
                message = self.gettext(u'"%s" is not a valid choice') % value
                raise ValidationError(message)

        if self.min_size is not None and len(result) < self.min_size:
            message = self.messages['too_small']
            if message is None:
                message = self.ngettext(
                    u'Please provide at least %d item.',
                    u'Please provide at least %d items.',
                    self.min_size) % self.min_size
            raise ValidationError(message)
        if self.max_size is not None and len(result) > self.max_size:
            message = self.messages['too_big']
            if message is None:
                message = self.ngettext(
                    u'Please provide no more than %d item.',
                    u'Please provide no more than %d items.',
                    self.min_size) % self.min_size
            raise ValidationError(message)

        return result

    def to_primitive(self, value):
        return map(unicode, _force_list(value))


class FloatField(Field):
    """Field for floating-point numbers.

    >>> field = FloatField(min_value=0,max_value=99.9)
    >>> field('13')
    13.0

    >>> field('13.123')
    13.122999999999999

    >>> field('thirteen')
    Traceback (most recent call last):
      ...
    ValidationError: Please enter a floating-point number.

    >>> field(101)
    Traceback (most recent call last):
      ...
    ValidationError: Ensure this value is less than or equal to 99.9.
    """

    messages = dict(
        too_small=None,
        too_big=None,
        no_float=None
    )

    def __init__(self, label=None, help_text=None, required=False,
                 min_value=None, max_value=None, validators=None,
                 widget=None, messages=None, sentinel=False):
        Field.__init__(self, label, help_text, validators, widget, messages,
                       sentinel)
        self.required = required
        self.min_value = min_value
        self.max_value = max_value

    def convert(self, value):
        value = _to_string(value)
        if not value:
            if self.required:
                message = self.messages['required']
                if message is None:
                    message = self.gettext(u'This field is required.')
                raise ValidationError(message)
            return None
        try:
            value = float(value)
        except ValueError:
            message = self.messages['no_float']
            if message is None:
                message = self.gettext('Please enter a floating-point number.')
            raise ValidationError(message)

        if self.min_value is not None and value < self.min_value:
            message = self.messages['too_small']
            if message is None:
                message = self.gettext(u'Ensure this value is greater than or '
                                       u'equal to %s.') % self.min_value
            raise ValidationError(message)
        if self.max_value is not None and value > self.max_value:
            message = self.messages['too_big']
            if message is None:
                message = self.gettext(u'Ensure this value is less than or '
                                       u'equal to %s.') % self.max_value
            raise ValidationError(message)

        return float(value)


class IntegerField(Field):
    """Field for integers.

    >>> field = IntegerField(min_value=0, max_value=99)
    >>> field('13')
    13

    >>> field('thirteen')
    Traceback (most recent call last):
      ...
    ValidationError: Please enter a whole number.

    >>> field('193')
    Traceback (most recent call last):
      ...
    ValidationError: Ensure this value is less than or equal to 99.
    """

    messages = dict(
        too_small=None,
        too_big=None,
        no_integer=None
    )

    def __init__(self, label=None, help_text=None, required=False,
                 min_value=None, max_value=None, validators=None,
                 widget=None, messages=None, sentinel=False):
        Field.__init__(self, label, help_text, validators, widget, messages,
                       sentinel)
        self.required = required
        self.min_value = min_value
        self.max_value = max_value

    def convert(self, value):
        value = _to_string(value)
        if not value:
            if self.required:
                message = self.messages['required']
                if message is None:
                    message = self.gettext(u'This field is required.')
                raise ValidationError(message)
            return None
        try:
            value = int(value)
        except ValueError:
            message = self.messages['no_integer']
            if message is None:
                message = self.gettext('Please enter a whole number.')
            raise ValidationError(message)

        if self.min_value is not None and value < self.min_value:
            message = self.messages['too_small']
            if message is None:
                message = self.gettext(u'Ensure this value is greater than or '
                                       u'equal to %s.') % self.min_value
            raise ValidationError(message)
        if self.max_value is not None and value > self.max_value:
            message = self.messages['too_big']
            if message is None:
                message = self.gettext(u'Ensure this value is less than or '
                                       u'equal to %s.') % self.max_value
            raise ValidationError(message)

        return int(value)


class BooleanField(Field):
    """Field for boolean values.

    >>> field = BooleanField()
    >>> field('1')
    True

    >>> field = BooleanField()
    >>> field('')
    False
    """

    widget = widgets.Checkbox
    validate_on_omission = True
    choices = [u'True', u'False']

    def convert(self, value):
        return value != u'False' and bool(value)

    def to_primitive(self, value):
        if self.convert(value):
            return u'True'
        return u'False'


class FormMeta(type):
    """Meta class for forms.  Handles form inheritance and registers
    validator functions.
    """

    def __new__(cls, name, bases, d):
        fields = {}
        validator_functions = {}
        root_validator_functions = []

        for base in reversed(bases):
            if hasattr(base, '_root_field'):
                # base._root_field is always a FormMapping field
                fields.update(base._root_field.fields)
                root_validator_functions.extend(base._root_field.validators)

        for key, value in d.iteritems():
            if key.startswith('validate_') and callable(value):
                validator_functions[key[9:]] = value
            elif isinstance(value, Field):
                fields[key] = value
                d[key] = FieldDescriptor(key)

        for field_name, func in validator_functions.iteritems():
            if field_name in fields:
                fields[field_name].validators.append(func)

        d['_root_field'] = root = FormMapping(**fields)
        context_validate = d.get('context_validate')
        root.validators.extend(root_validator_functions)
        if context_validate is not None:
            root.validators.append(context_validate)

        return type.__new__(cls, name, bases, d)

    def as_field(cls):
        """Returns a field object for this form.  The field object returned
        is independent of the form and can be modified in the same manner as
        a bound field.
        """
        field = object.__new__(FormAsField)
        field.__dict__.update(cls._root_field.__dict__)
        field.form_class = cls
        field.validators = cls._root_field.validators[:]
        field.fields = cls._root_field.fields.copy()
        return field

    @property
    def validators(cls):
        return cls._root_field.validators

    @property
    def fields(cls):
        return cls._root_field.fields


class FieldDescriptor(object):

    def __init__(self, name):
        self.name = name

    def __get__(self, obj, type=None):
        try:
            return (obj or type).fields[self.name]
        except KeyError:
            raise AttributeError(self.name)

    def __set__(self, obj, value):
        obj.fields[self.name] = value

    def __delete__(self, obj):
        if self.name not in obj.fields:
            raise AttributeError('%r has no attribute %r' %
                                 (type(obj).__name__, self.name))
        del obj.fields[self.name]


class FormBase(object):
    """Form base class.

    >>> class PersonForm(FormBase):
    ...     name = TextField(required=True)
    ...     age = IntegerField()

    >>> form = PersonForm()
    >>> form.validate({'name': 'johnny', 'age': '42'})
    True
    >>> form.data['name']
    u'johnny'
    >>> form.data['age']
    42

    Let's cause a simple validation error:

    >>> form = PersonForm()
    >>> form.validate({'name': '', 'age': 'fourty-two'})
    False
    >>> print form.errors['age'][0]
    Please enter a whole number.
    >>> print form.errors['name'][0]
    This field is required.

    You can also add custom validation routines for fields by adding methods
    that start with the prefix ``validate_`` and the field name that take the
    value as argument. For example:

    >>> class PersonForm(FormBase):
    ...     name = TextField(required=True)
    ...     age = IntegerField()
    ...
    ...     def validate_name(self, value):
    ...         if not value.isalpha():
    ...             message = u'The value must only contain letters'
    ...             raise ValidationError(message)

    >>> form = PersonForm()
    >>> form.validate({'name': 'mr.t', 'age': '42'})
    False
    >>> form.errors
    {'name': [u'The value must only contain letters']}

    You can also validate multiple fields in the context of other fields.
    That validation is performed after all other validations.  Just add a
    method called ``context_validate`` that is passed the dict of all fields:

    >>> class RegisterForm(FormBase):
    ...     username = TextField(required=True)
    ...     password = TextField(required=True)
    ...     password_again = TextField(required=True)
    ...
    ...     def context_validate(self, data):
    ...         if data['password'] != data['password_again']:
    ...             message = u'The two passwords must be the same'
    ...             raise ValidationError(message)
    ...
    >>> form = RegisterForm()
    >>> form.validate({'username': 'admin', 'password': 'blah',
    ...                'password_again': 'blag'})
    ...
    False
    >>> form.errors
    {None: [u'The two passwords must be the same']}

    Forms can be used as fields for other forms.  To create a form field of
    a form you can call the `as_field` class method::

    >>> field = RegisterForm.as_field()

    This field can be used like any other field class.  What's important about
    forms as fields is that validators don't get an instance of `RegisterForm`
    passed as `form` / `self` but the form where it's used in if the field is
    used from a form.

    Form fields are bound to the form on form instanciation.  This makes it
    possible to modify a particular instance of the form.  For example you
    can create an instance of it and drop some fields by using
    ``del form.fields['name']`` or reassign choices of choice fields.  It's
    however not easily possible to add new fields to an instance because newly
    added fields wouldn't be bound.  The fields that are stored directly on
    the form can also be accessed with their name like a regular attribute.

    Example usage:

    >>> class StatusForm(FormBase):
    ...     status = ChoiceField()
    ...
    >>> StatusForm.status.bound
    False
    >>> form = StatusForm()
    >>> form.status.bound
    True
    >>> form.status.choices = [u'happy', u'unhappy']
    >>> form.validate({'status': u'happy'})
    True
    >>> form['status']
    u'happy'

    Forms can be recaptcha protected by setting `captcha_protected` to `True`.
    If captcha protection is enabled the captcha has to be rendered from the
    widget created, like a field.

    Forms are CSRF protected if they are created in the context of an active
    request or if an request is passed to the constructor.  In order for the
    CSRF protection to work it will modify the session on the request.

    The consequence of that is that the application must not ignore session
    changes.
    """
    __metaclass__ = FormMeta

    csrf_protected = None
    redirect_tracking = True
    allowed_redirect_rules = None
    captcha_protected = False
    default_method = 'POST'
    html_builder = html

    recaptcha_public_key = None
    recaptcha_private_key = None
    recaptcha_use_ssl = True

    def __init__(self, initial=None, action=None, request_info=None):
        if request_info is None:
            request_info = self._lookup_request_info()
        self.request_info = request_info
        if initial is None:
            initial = {}
        self.initial = initial
        self.action = action
        self.invalid_redirect_targets = set()

        if self.request_info is not None:
            if self.csrf_protected is None:
                self.csrf_protected = True
            if self.action in (None, u'', u'.'):
                self.action = self._get_default_action()
            else:
                self.action = urljoin(self._get_request_url(), self.action)
        elif self.csrf_protected is None:
            self.csrf_protected = False

        if self.action is None:
            self.action = u''

        self._root_field = _bind(self.__class__._root_field, self, {})
        self.reset()

    def __getitem__(self, key):
        return self.data[key]

    def __contains__(self, key):
        return key in self.data

    def as_widget(self):
        """Return the form as widget."""
        # if there is submitted data, use that for the widget
        if self.raw_data is not None:
            data = self.raw_data
        # otherwise go with the data from the source (eg: database)
        else:
            data = self.data
        return _make_widget(self._root_field, None, data, self.errors)

    def add_invalid_redirect_target(self, *args, **kwargs):
        """Add an invalid target. Invalid targets are URLs we don't want to
        visit again. For example if a post is deleted from the post edit page
        it's a bad idea to redirect back to the edit page because in that
        situation the edit page would return a page not found.

        This function accepts the same parameters as `url_for`.
        """
        self.invalid_redirect_targets.add(self._resolve_url(args, kwargs))

    @property
    def redirect_target(self):
        """The back-redirect target for this form."""
        return self._get_valid_redirect_target()

    def redirect(self, *args, **kwargs):
        """Redirects to the url rule given or back to the URL where we are
        comming from if `redirect_tracking` is enabled.
        """
        target = None
        if self.redirect_tracking:
            target = self.redirect_target
        if target is None:
            return self._redirect_to_url(self._resolve_url(args, kwargs))
        return self._redirect_to_url(target)

    @property
    def csrf_token(self):
        """The unique CSRF security token for this form."""
        if not self.csrf_protected:
            raise AttributeError('no csrf token because form not '
                                 'csrf protected')
        return get_csrf_token(self._get_session(), self.action)

    @property
    def is_valid(self):
        """True if the form is valid."""
        return not self.errors

    @property
    def has_changed(self):
        """True if the form has changed."""
        return self._root_field.to_primitive(self.initial) != \
               self._root_field.to_primitive(self.data)

    @property
    def fields(self):
        return self._root_field.fields

    @property
    def validators(self):
        return self._root_field.validators

    def reset(self):
        """Resets the form."""
        self.data = self.initial.copy()
        self.errors = {}
        self.raw_data = None

    def add_error(self, error, field=None):
        """Adds an error to a field."""
        seq = self.errors.get(field)
        if seq is None:
            seq = self.errors[field] = widgets.ErrorList(self)
        seq.append(error)

    def validate(self, data=None, from_flat=True):
        """Validate the form against the data passed.  If no data is provided
        the form data of the current request is taken.  By default a flat
        representation of the data is assumed.  If you already have a non-flat
        representation of the data (JSON for example) you can disable that
        with ``from_flat=False``.
        """
        if data is None:
            data = self._autodiscover_data()
        if from_flat:
            data = decode_form_data(data)
        self.raw_data = data

        # for each field in the root that requires validation on value
        # omission we add `None` into the raw data dict.  Because the
        # implicit switch between initial data and user submitted data
        # only happens on the "root level" for obvious reasons we only
        # have to hook the data in here.
        for name, field in self._root_field.fields.iteritems():
            if field.validate_on_omission and name not in self.raw_data:
                self.raw_data.setdefault(name)

        d = self.data.copy()
        d.update(self.raw_data)
        errors = {}
        try:
            data = self._root_field(d)
        except ValidationError, e:
            errors = e.unpack(self)
        self.errors = errors

        # every time we validate, we invalidate the csrf token if there
        # was one.
        if self.csrf_protected:
            # FIXME: do we really want action here?
            invalidate_csrf_token(self._get_session(), self.action)

        if errors:
            return False

        self.data.update(data)
        return True

    # extra functionality that has to be implemented

    def _get_translations(self):
        """Has to return a gettext translations object that supports
        unicode.  By default a dummy is returned.
        """
        return _dummy_translations

    def _lookup_request_info(self):
        """Called if no request info is passed to the form.  Might lookup
        the request info from a thread local storage.
        """
        return None

    def _get_wsgi_environ(self):
        """Return the WSGI environment from the request info if possible."""
        return None

    def _get_default_action(self):
        """Returns the default action if no action is given.  If this method
        returns `None` an empty default action is used which will always
        submit to the same URL.
        """
        return None

    def _get_request_url(self):
        """Returns the current URL of the request.  When this is called,
        `self.request_info` is set to the request info passed or the
        one looked up by `_lookup_request_info`.
        """
        env = self._get_wsgi_environ()
        if env is not None:
            return get_current_url(env)
        return ''

    def _autodiscover_data(self):
        """Called by `validate` if no data is provided.  Finds the
        matching data from the request object by default depending
        on the default submit method of the form.
        """
        raise NotImplementedError(
            'No data passed to the validation and data auto discovery not '
            'implemented.  Override the `_autodiscover_data` method.')

    def _get_redirect_user_url(self):
        """Returns the user URL.  By default only the `_redirect_target` from
        the form is taken into account.  You can override this if you want
        to support an URL `next` parameter.
        """
        # FIXME: raw_data is still none, is this wanted?
        return (None if self.raw_data is None else
                self.raw_data.get('_redirect_target'))

    def _get_valid_redirect_target(self):
        environ = self._get_wsgi_environ()
        if environ is None:
            raise NotImplementedError(
                'the default `_get_valid_redirect_target` requires '
                '`_get_wsgi_environ` to return a WSGI environment.')
        user_url = self._get_redirect_user_url()
        return get_redirect_target(environ, user_url,
                                   self.invalid_redirect_targets,
                                   self.allowed_redirect_rules)

    def _redirect_to_url(self, url):
        raise NotImplementedError(
            'if you want to use redirects you have to implement the '
            '`_redirect_to_url` method.')

    def _resolve_url(self, args, kwargs):
        if len(args) == 1:
            return args[0]
        raise NotImplementedError(
            '`_resolve_url` does not know how to handle the arguments that '
            'were forwarded.  If you want to integrate your own url system, '
            'implement a different logic into that method.')

    def _get_session(self):
        raise NotImplementedError(
            'some features require access to the session.  If you want those, '
            'implement `_get_session`.')

    def _get_remote_addr(self):
        return self._get_wsgi_environ()['REMOTE_ADDR']
