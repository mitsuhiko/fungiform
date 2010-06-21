# -*- coding: utf-8 -*-
"""
    fungiform.widgets
    ~~~~~~~~~~~~~~~~~

    The widgets.

    :copyright: (c) 2010 by the Fungiform Team.
    :license: BSD, see LICENSE for more details.
"""
from itertools import chain

from fungiform.utils import make_name, _force_dict, _make_widget,\
                            _value_matches_choice, _force_list,\
                            _to_string, _to_list, Markup, soft_unicode
from fungiform.recaptcha import get_recaptcha_html


def _add_class(attrs, classname):
    """Adds a class to an attribute dict"""
    attrs['class'] = u' '.join(filter(None, [attrs.pop('class', u''),
                                             attrs.pop('class_', u'')]) +
                               [classname])


def _iter_choices(choices):
    """Iterate over choices."""
    if choices is not None:
        for choice in choices:
            if not isinstance(choice, tuple):
                choice = (choice, choice)
            yield choice


def _is_choice_selected(field, value, choice):
    """Checks if a choice is selected.  If the field is a multi select
    field it's checked if the choice is in the passed iterable of values,
    otherwise it's checked if the value matches the choice.
    """
    if field.multiple_choices:
        for value in value:
            if _value_matches_choice(value, choice):
                return True
        return False
    return _value_matches_choice(value, choice)


class _Renderable(object):
    """Mixin for renderable HTML objects."""

    def render(self):
        return u''

    def __call__(self, *args, **kwargs):
        return self.render(*args, **kwargs)


class Widget(_Renderable):
    """Baseclass for all widgets.  All widgets share a common interface
    that can be used from within templates.

    Take this form as an example:

    >>> from fungiform.forms import FormBase, TextField, MultiChoiceField
    >>> class LoginForm(FormBase):
    ...     username = TextField(required=True)
    ...     password = TextField(widget=PasswordInput)
    ...     flags = MultiChoiceField(choices=[1, 2, 3])
    ...
    >>> form = LoginForm()
    >>> form.validate({'username': '', 'password': '',
    ...                'flags': [1, 3]})
    False
    >>> widget = form.as_widget()

    You can get the subwidgets by using the normal indexing operators:

    >>> username = widget['username']
    >>> password = widget['password']

    To render a widget you can usually invoke the `render()` method.  All
    keyword parameters are used as HTML attribute in the resulting tag.
    You can also call the widget itself (``username()`` instead of
    ``username.render()``) which does the same if there are no errors for
    the field but adds the default error list after the widget if there
    are errors.

    Widgets have some public attributes:

    `errors`

        gives the list of errors:

        >>> username.errors
        [u'This field is required.']

        This error list is printable:

        >>> print username.errors()
        <ul class="errors"><li>This field is required.</li></ul>

        Like any other sequence that yields list items it provides
        `as_ul` and `as_ol` methods:

        >>> print username.errors.as_ul()
        <ul><li>This field is required.</li></ul>

        Keep in mind that ``widget.errors()`` is equivalent to
        ``widget.errors.as_ul(class_='errors', hide_empty=True)``.

    `value`

        returns the value of the widget as primitive.  For basic
        widgets this is always a string, for widgets with subwidgets or
        widgets with multiple values a dict or a list:

        >>> username.value
        u''
        >>> widget['flags'].value
        [u'1', u'3']

    `name` gives you the name of the field for form submissions:

        >>> username.name
        'username'

        Please keep in mind that the name is not always that obvious.  This
        form system supports nested form fields so it's a good idea to
        always use the name attribute.

    `id`

        gives you the default domain for the widget.  This is either none
        if there is no idea for the field or `f_` + the field name with
        underscores instead of dots:

        >>> username.id
        'f_username'

    `all_errors`

        like `errors` but also contains the errors of child widgets.
    """

    disable_dt = False

    def __init__(self, field, name, value, all_errors):
        self._form = field.form
        self._field = field
        self._value = value
        self._all_errors = all_errors
        self.name = name

    @property
    def empty_as_item(self):
        """Works like the method on the field just for the widget plus
        the bound value.
        """
        return self._field.empty_as_item(self.value)

    def hidden(self):
        """Return one or multiple hidden fields for the current value.  This
        also handles subwidgets.  This is useful for transparent form data
        passing.
        """
        fields = []

        def _add_field(name, value):
            html = self._field.form.html_builder
            fields.append(html.input(type='hidden', name=name, value=value))

        def _to_hidden(value, name):
            if isinstance(value, list):
                for idx, value in enumerate(value):
                    _to_hidden(value, make_name(name, idx))
            elif isinstance(value, dict):
                for key, value in value.iteritems():
                    _to_hidden(value, make_name(name, key))
            else:
                _add_field(name, value)

        _to_hidden(self.value, self.name)
        return u'\n'.join(fields)

    @property
    def localname(self):
        """The local name of the field."""
        return self.name.rsplit('.', 1)[-1]

    @property
    def id(self):
        """The proposed id for this widget."""
        if self.name is not None:
            return 'f_' + self.name.replace('.', '__')

    @property
    def value(self):
        """The primitive value for this widget."""
        return self._field.to_primitive(self._value)

    @property
    def label(self):
        """The label for the widget."""
        if self._field.label is not None:
            return Label(self._field, soft_unicode(self._field.label), self.id)

    @property
    def help_text(self):
        """The help text of the widget."""
        if self._field.help_text is not None:
            return unicode(self._field.help_text)

    @property
    def errors(self):
        """The direct errors of this widget."""
        if self.name in self._all_errors:
            return self._all_errors[self.name]
        return ErrorList(self._field.form)

    @property
    def all_errors(self):
        """The current errors and the errors of all child widgets."""
        items = sorted(self._all_errors.items())
        if self.name is None:
            return ErrorList(self._field.form,
                             chain(*(item[1] for item in items)))
        result = ErrorList(self._field.form)
        for key, value in items:
            if key == self.name or (key is not None and
                                    key.startswith(self.name + '.')):
                result.extend(value)
        return result

    @property
    def default_display_errors(self):
        """The errors that should be displayed."""
        return self.errors

    def as_dd(self, **attrs):
        """Return a dt/dd item."""
        html = self._field.form.html_builder
        rv = []
        if not self.disable_dt:
            label = self.label
            if label:
                rv.append(html.dt(label()))
        rv.append(html.dd(self(**attrs)))
        if self.help_text:
            rv.append(html.dd(self.help_text, class_='explanation'))
        return Markup(u''.join(rv))

    def _attr_setdefault(self, attrs):
        """Add an ID to the attrs if there is none."""
        if 'id' not in attrs and self.id is not None:
            attrs['id'] = self.id

    def __call__(self, **attrs):
        """The default display is the form + error list as ul if needed."""
        return self.render(**attrs) + self.default_display_errors()


class Label(_Renderable):
    """Holds a label."""

    def __init__(self, field, text, linked_to=None):
        self._field = field
        self.text = text
        self.linked_to = linked_to

    def render(self, **attrs):
        html = self._field.form.html_builder
        attrs.setdefault('for', self.linked_to)
        return html.label(self.text, **attrs)


class InternalWidget(Widget):
    """Special widgets are widgets that can't be used on arbitrary
    form fields but belong to others.
    """

    def __init__(self, parent):
        self._parent = parent

    errors = all_errors = property(lambda x: ErrorList(x._parent._field.form))
    value = name = None


class Input(Widget):
    """A widget that is a HTML input field."""
    hide_value = False
    type = None

    def render(self, **attrs):
        html = self._field.form.html_builder
        self._attr_setdefault(attrs)
        value = self.value
        if self.hide_value:
            value = u''
        return html.input(name=self.name, value=value, type=self.type,
                          **attrs)


class TextInput(Input):
    """A widget that holds text."""
    type = 'text'


class PasswordInput(TextInput):
    """A widget that holds a password."""
    type = 'password'
    hide_value = True


class HiddenInput(Input):
    """A hidden input field for text."""
    type = 'hidden'


class Textarea(Widget):
    """Displays a textarea."""

    @property
    def default_display_errors(self):
        """A textarea is often used with multiple, it makes sense to
        display the errors of all childwidgets then which are not
        renderable because they are text.
        """
        return self.all_errors

    def _attr_setdefault(self, attrs):
        Widget._attr_setdefault(self, attrs)
        attrs.setdefault('rows', 8)
        attrs.setdefault('cols', 40)

    def render(self, **attrs):
        html = self._field.form.html_builder
        self._attr_setdefault(attrs)
        return html.textarea(self.value, name=self.name, **attrs)


class Checkbox(Widget):
    """A simple checkbox."""

    @property
    def checked(self):
        return self.value != u'False'

    def with_help_text(self, **attrs):
        """Render the checkbox with help text."""
        html = self._field.form.html_builder
        data = self(**attrs)
        if self.help_text:
            data += u' ' + html.label(self.help_text, class_='explanation',
                                      for_=self.id)
        return Markup(data)

    def as_dd(self, **attrs):
        """Return a dt/dd item."""
        html = self._field.form.html_builder
        rv = []
        label = self.label
        if label:
            rv.append(html.dt(label()))
        rv.append(html.dd(self.with_help_text()))
        return Markup(u''.join(rv))

    def as_li(self, **attrs):
        """Return a li item."""
        html = self._field.form.html_builder
        rv = [self.render(**attrs)]
        if self.label:
            rv.append(u' ' + self.label())
        if self.help_text:
            rv.append(html.div(self.help_text, class_='explanation'))
        rv.append(self.default_display_errors())
        return html.li(u''.join(rv))

    def render(self, **attrs):
        html = self._field.form.html_builder
        self._attr_setdefault(attrs)
        return html.input(name=self.name, type='checkbox',
                          checked=self.checked, **attrs)


class SelectBox(Widget):
    """A select box."""

    def _attr_setdefault(self, attrs):
        Widget._attr_setdefault(self, attrs)
        attrs.setdefault('multiple', self._field.multiple_choices)

    def render(self, **attrs):
        html = self._field.form.html_builder
        self._attr_setdefault(attrs)
        items = []
        for choice in self._field.choices:
            if isinstance(choice, tuple):
                key, value = choice
            else:
                key = value = choice
            selected = _is_choice_selected(self._field, self.value, key)
            items.append(html.option(unicode(value), value=unicode(key),
                                     selected=selected))
        return html.select(name=self.name, *items, **attrs)


class _InputGroupMember(InternalWidget):
    """A widget that is a single radio button."""

    # override the label descriptor
    label = None
    inline_label = True

    def __init__(self, parent, value, label):
        InternalWidget.__init__(self, parent)
        self.value = unicode(value)
        self.label = Label(self._parent._field, label, self.id)

    @property
    def name(self):
        return self._parent.name

    @property
    def id(self):
        return 'f_%s_%s' % (self._parent.name, self.value)

    @property
    def checked(self):
        return _is_choice_selected(self._parent._field, self._parent.value,
                                   self.value)

    def render(self, **attrs):
        html = self._parent._field.form.html_builder
        self._attr_setdefault(attrs)
        return html.input(type=self.type, name=self.name, value=self.value,
                          checked=self.checked, **attrs)


class RadioButton(_InputGroupMember):
    """A radio button in an input group."""
    type = 'radio'


class GroupCheckbox(_InputGroupMember):
    """A checkbox in an input group."""
    type = 'checkbox'


class _InputGroup(Widget):

    def __init__(self, field, name, value, all_errors):
        Widget.__init__(self, field, name, value, all_errors)
        self.choices = []
        self._subwidgets = {}
        for value, label in _iter_choices(self._field.choices):
            widget = self.subwidget(self, value, label)
            self.choices.append(widget)
            self._subwidgets[value] = widget

    def __getitem__(self, value):
        """Return a subwidget."""
        return self._subwidgets[value]

    def _as_list(self, list_type, attrs):
        _ = self._field.form._get_translations().ugettext
        if attrs.pop('hide_empty', False) and not self.choices:
            return u''
        self._attr_setdefault(attrs)
        empty_msg = attrs.pop('empty_msg', None)
        label = not attrs.pop('nolabel', False)
        class_ = attrs.pop('class_', attrs.pop('class', None))
        if class_ is None:
            class_ = 'choicegroup'
        attrs['class'] = class_
        choices = [Markup(u'<li>%s %s</li>') % (
            choice(),
            label and choice.label() or u''
        ) for choice in self.choices]
        if not choices:
            if empty_msg is None:
                empty_msg = _('No choices.')
            choices.append(Markup(u'<li>%s</li>') % _(empty_msg))
        return Markup(list_type(*choices, **attrs))

    def as_ul(self, **attrs):
        """Render the radio buttons widget as <ul>"""
        html = self._field.form.html_builder
        return self._as_list(html.ul, attrs)

    def as_ol(self, **attrs):
        """Render the radio buttons widget as <ol>"""
        html = self._field.form.html_builder
        return self._as_list(html.ol, attrs)

    def as_table(self, **attrs):
        """Render the radio buttons widget as <table>"""
        self._attr_setdefault(attrs)
        return Markup(list_type(*[u'<tr><td>%s</td><td>%s</td></tr>' % (
            choice,
            choice.label
        ) for choice in self.choices], **attrs))

    def render(self, **attrs):
        return self.as_ul(**attrs)


class RadioButtonGroup(_InputGroup):
    """A group of radio buttons."""
    subwidget = RadioButton


class CheckboxGroup(_InputGroup):
    """A group of checkboxes."""
    subwidget = GroupCheckbox


class MappingWidget(Widget):
    """Special widget for dict-like fields."""

    def __init__(self, field, name, value, all_errors):
        Widget.__init__(self, field, name, _force_dict(value), all_errors)
        self._subwidgets = {}

    def __getitem__(self, name):
        subwidget = self._subwidgets.get(name)
        if subwidget is None:
            # this could raise a KeyError we pass through
            subwidget = _make_widget(self._field.fields[name],
                                     make_name(self.name, name),
                                     self._value.get(name),
                                     self._all_errors)
            self._subwidgets[name] = subwidget
        return subwidget

    def as_dl(self, **attrs):
        _add_class(attrs, 'mapping')
        html = self._field.form.html_builder
        return html.dl(*[x.as_dd() for x in self], **attrs)

    def __call__(self, *args, **kwargs):
        return self.as_dl(*args, **kwargs)

    def __iter__(self):
        for key in self._field.fields:
            yield self[key]


class FormWidget(MappingWidget):
    """A widget for forms."""

    def get_hidden_fields(self):
        """This method is called by the `hidden_fields` property to return
        a list of (key, value) pairs for the special hidden fields.
        """
        fields = []
        if self._field.form.request_info is not None:
            if self._field.form.csrf_protected:
                fields.append(('_csrf_token', self.csrf_token))
            if self._field.form.redirect_tracking:
                target = self.redirect_target
                if target is not None:
                    fields.append(('_redirect_target', target))
        return fields

    @property
    def hidden_fields(self):
        """The hidden fields as string."""
        html = self._field.form.html_builder
        return u''.join(html.input(type='hidden', name=name, value=value)
                        for name, value in self.get_hidden_fields())

    @property
    def captcha(self):
        """The captcha if one exists for this form."""
        if hasattr(self, '_captcha'):
            return self._captcha
        captcha = None
        if self._field.form.captcha_protected:
            captcha = get_recaptcha_html(self._field.form.recaptcha_public_key,
                                         self._field.form.recaptcha_use_ssl)
        self._captcha = captcha
        return captcha

    @property
    def csrf_token(self):
        """Forward the CSRF check token for templates."""
        return self._field.form.csrf_token

    @property
    def redirect_target(self):
        """The redirect target for this form."""
        return self._field.form.redirect_target

    def default_actions(self, **attrs):
        """Returns a default action div with a submit button."""
        html = self._field.form.html_builder
        label = attrs.pop('label', None)
        if label is None:
            label = self._field.form._get_translations().ugettext('Submit')
        attrs.setdefault('class', 'actions')
        return html.div(html.input(type='submit', value=label), **attrs)

    def render(self, method=None, **attrs):
        html = self._field.form.html_builder
        self._attr_setdefault(attrs)
        with_errors = attrs.pop('with_errors', False)
        if method is None:
            method = self._field.form.default_method.lower()

        # support jinja's caller
        caller = attrs.pop('caller', None)
        if caller is not None:
            body = caller()
        else:
            body = self.as_dl() + self.default_actions()

        hidden = self.hidden_fields
        if hidden:
            # if there are hidden fields we put an invisible div around
            # it.  the HTML standard doesn't allow input fields as direct
            # childs of a <form> tag...
            body = Markup('<div style="display: none">%s</div>%s'
                              % (hidden, body))

        if with_errors:
            body = self.default_display_errors() + body
        return html.form(body, action=self._field.form.action,
                         method=method, **attrs)

    def __call__(self, *args, **attrs):
        attrs.setdefault('with_errors', True)
        return self.render(*args, **attrs)


class ListWidget(Widget):
    """Special widget for list-like fields."""

    def __init__(self, field, name, value, all_errors):
        Widget.__init__(self, field, name, _force_list(value), all_errors)
        self._subwidgets = {}

    def as_ul(self, **attrs):
        html = self._field.form.html_builder
        return self._as_list(html.ul, attrs)

    def as_ol(self, **attrs):
        html = self._field.form.html_builder
        return self._as_list(html.ol, attrs)

    def _as_list(self, factory, attrs):
        if attrs.pop('hide_empty', False) and not self:
            return u''
        _add_class(attrs, 'multiple-items')
        html = self._field.form.html_builder
        items = []
        empty_streak = 0
        for index in xrange(len(self)):
            subwidget = self[index]
            empty_streak = empty_streak + 1 if subwidget.empty_as_item else 0
            items.append(html.li(subwidget()))

        # insert empty widgets at the end if necessary
        for offset in xrange(attrs.pop('extra_rows', 1) - empty_streak):
            items.append(html.li(self[len(items) + offset + 1]()))

        return factory(*items, **attrs)

    def __getitem__(self, index):
        if not isinstance(index, (int, long)):
            raise TypeError('list widget indices must be integers')
        subwidget = self._subwidgets.get(index)
        if subwidget is None:
            try:
                value = self._value[index]
            except IndexError:
                # return an widget without value if we try
                # to access a field not in the list
                value = None
            subwidget = _make_widget(self._field.field,
                                     make_name(self.name, index), value,
                                     self._all_errors)
            self._subwidgets[index] = subwidget
        return subwidget

    def __iter__(self):
        for index in xrange(len(self)):
            yield self[index]

    def __len__(self):
        return len(self._value)

    def __call__(self, *args, **kwargs):
        return self.as_ul(*args, **kwargs)


class ErrorList(_Renderable, list):
    """The class that is used to display the errors."""

    def __init__(self, form, *args):
        self._form = form
        super(ErrorList, self).__init__(*args)

    def render(self, **attrs):
        return self.as_ul(**attrs)

    def as_ul(self, **attrs):
        html = self._form.html_builder
        return self._as_list(html.ul, attrs)

    def as_ol(self, **attrs):
        html = self._form.html_builder
        return self._as_list(html.ol, attrs)

    def _as_list(self, factory, attrs):
        html = self._form.html_builder
        if attrs.pop('hide_empty', False) and not self:
            return u''
        return factory(*(html.li(item) for item in self), **attrs)

    def __call__(self, **attrs):
        attrs.setdefault('class', attrs.pop('class_', 'errors'))
        attrs.setdefault('hide_empty', True)
        return self.render(**attrs)
