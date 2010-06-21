# -*- coding: utf-8 -*-
"""
    fungiform.tests.forms
    ~~~~~~~~~~~~~~~~~~~~~

    The unittests for the forms.

    :copyright: (c) 2010 by the Fungiform Team.
    :license: BSD, see LICENSE for more details.
"""
import unittest
from fungiform import forms


class FormTestCase(unittest.TestCase):

    def test_simple_form(self):
        class MyForm(forms.FormBase):
            username = forms.TextField()
            item_count = forms.IntegerField()
            is_active = forms.BooleanField()

        form = MyForm()
        form.validate({
            'username':     'foobar',
            'item_count':   '42',
            'is_active':    'a value'
        })

        self.assertEqual(form.raw_data['username'], 'foobar')
        self.assertEqual(form.raw_data['item_count'], '42')
        self.assertEqual(form.raw_data['is_active'], 'a value')

        self.assertEqual(form.data['username'], 'foobar')
        self.assertEqual(form.data['item_count'], 42)
        self.assertEqual(form.data['is_active'], True)

    def test_simple_nesting(self):
        class MyForm(forms.FormBase):
            ints = forms.Multiple(forms.IntegerField())
            strings = forms.CommaSeparated(forms.TextField())

        form = MyForm()
        form.validate({
            'ints.0':       '42',
            'ints.1':       '125',
            'ints.55':      '23',
            'strings':      'foo, bar, baz'
        })

        self.assertEqual(form.data['ints'], [42, 125, 23])
        self.assertEqual(form.data['strings'], 'foo bar baz'.split())

    def test_form_as_field(self):
        class AddressForm(forms.FormBase):
            street = forms.TextField()
            zipcode = forms.IntegerField()

        class MyForm(forms.FormBase):
            username = forms.TextField()
            addresses = forms.Multiple(AddressForm.as_field())

        form = MyForm()
        form.validate({
            'username':     'foobar',
            'addresses.0.street':   'Ici',
            'addresses.0.zipcode':  '11111',
            'addresses.2.street':   'Ailleurs',
            'addresses.2.zipcode':  '55555',
        })
        self.assertEqual(form.data, {
            'username': u'foobar',
            'addresses': [{'street': u'Ici', 'zipcode': 11111},
                          {'street': u'Ailleurs', 'zipcode': 55555}],
        })


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(FormTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
