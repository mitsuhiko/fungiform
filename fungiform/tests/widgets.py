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


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(WidgetTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
