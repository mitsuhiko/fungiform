# -*- coding: utf-8 -*-
"""
    fungiform.tests.widgets
    ~~~~~~~~~~~~~~~~~~~~~~~

    The unittests for the widgets.

    :copyright: (c) 2010 by the Fungiform Team.
    :license: BSD, see LICENSE for more details.
"""
import unittest
from fungiform import forms, widgets


class WidgetTestCase(unittest.TestCase):

    def test_multichoice(self):
        class MyForm(forms.FormBase):
            mc = forms.MultiChoiceField('Foo',
                                        choices=[(1, 'One'), (2, 'Two')],
                                        widget=widgets.CheckboxGroup)
        self.assertEqual(
            u'<form action="" method="post">'
            u'<dl class="mapping">'
              u'<dt><label for="f_mc">Foo</label></dt>'
              u'<dd>'
                u'<ul id="f_mc" class="choicegroup">'
                  u'<li><input type="checkbox" id="f_mc_1" value="1" '
                        u'name="mc"> <label for="f_mc_1">One</label></li>'
                  u'<li><input type="checkbox" id="f_mc_2" value="2" '
                        u'name="mc"> <label for="f_mc_2">Two</label></li>'
                u'</ul>'
              u'</dd>'
            u'</dl>'
            u'<div class="actions"><input type="submit" value="Submit"></div>'
            u'</form>', MyForm().as_widget().render())

    def test_form_as_field(self):
        class AddressForm(forms.FormBase):
            street = forms.TextField()
            zipcode = forms.IntegerField()

        class MyForm(forms.FormBase):
            username = forms.TextField()
            addresses = forms.Multiple(AddressForm.as_field())

        form = MyForm()
        self.assertEqual(
            u'<form action="" method="post">'
              u'<dl class="mapping">'
                u'<dd><input type="text" id="f_username" value="" '
                           u'name="username"></dd>'
                u'<dd>'
                  u'<ul class="multiple-items">'
                    u'<li><dl class="mapping">'
                      u'<dd><input type="text" id="f_addresses__0__street" '
                            u'value="" name="addresses.0.street"></dd>'
                      u'<dd><input type="text" id="f_addresses__0__zipcode" '
                            u'value="" name="addresses.0.zipcode"></dd>'
                    u'</dl></li>'
                  u'</ul>'
                u'</dd>'
              u'</dl>'
              u'<div class="actions">'
                u'<input type="submit" value="Submit"></div>'
            u'</form>', form.as_widget().render())

        form.validate({
            'username':     'foobar',
            'addresses.0.street':   'Ici',
            'addresses.0.zipcode':  '11111',
            'addresses.2.street':   'Ailleurs',
            'addresses.2.zipcode':  '55555',
        })
        self.assertEqual(
            u'<form action="" method="post">'
              u'<dl class="mapping">'
                u'<dd><input type="text" id="f_username" value="foobar" '
                           u'name="username"></dd>'
                u'<dd>'
                  u'<ul class="multiple-items">'
                    u'<li><dl class="mapping">'
                      u'<dd><input type="text" id="f_addresses__0__street" '
                            u'value="Ici" name="addresses.0.street"></dd>'
                      u'<dd><input type="text" id="f_addresses__0__zipcode" '
                            u'value="11111" name="addresses.0.zipcode"></dd>'
                    u'</dl></li>'
                    u'<li><dl class="mapping">'
                      u'<dd><input type="text" id="f_addresses__1__street" '
                            u'value="Ailleurs" name="addresses.1.street"></dd>'
                      u'<dd><input type="text" id="f_addresses__1__zipcode" '
                            u'value="55555" name="addresses.1.zipcode"></dd>'
                    u'</dl></li>'
                    u'<li><dl class="mapping">'
                      u'<dd><input type="text" id="f_addresses__2__street" '
                            u'value="" name="addresses.2.street"></dd>'
                      u'<dd><input type="text" id="f_addresses__2__zipcode" '
                            u'value="" name="addresses.2.zipcode"></dd>'
                    u'</dl></li>'
                  u'</ul>'
                u'</dd>'
              u'</dl>'
              u'<div class="actions">'
                u'<input type="submit" value="Submit"></div>'
            u'</form>', form.as_widget().render())
        self.assertEqual(
            u'<input type="text" id="f_username" value="foobar" '
            u'name="username">', form.as_widget()['username']())
        self.assertEqual(
            u'<input type="text" id="f_addresses__0__zipcode" value="11111" '
            u'name="addresses.0.zipcode">',
            form.as_widget()['addresses'][0]['zipcode']())
        self.assertEqual(
            u'<input type="text" id="f_addresses__42__street" value="" '
            u'name="addresses.42.street">',
            form.as_widget()['addresses'][42]['street']())


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(WidgetTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
