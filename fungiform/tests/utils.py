# -*- coding: utf-8 -*-
"""
    fungiform.tests.utils
    ~~~~~~~~~~~~~~~~~~~~~

    Unittests for the utilities.

    :copyright: (c) 2010 by the Fungiform Team.
    :license: BSD, see LICENSE for more details.
"""
import unittest
from fungiform import utils


class WebObLikeDict(object):

    def items(self):
        yield 'key1', 'value1'
        yield 'key1', 'value2'
        yield 'key1', 'value3'
        yield 'key2', 'awesome'


class WerkzeugLikeDict(object):

    def iterlists(self):
        yield 'key1', ['value1', 'value2', 'value3']
        yield 'key2', ['awesome']


class UtilsTestCase(unittest.TestCase):

    assertEq = unittest.TestCase.assertEqual

    def assertEqual(self, first, second, msg=None):
        # compare both type and value
        self.assertEq(first, second, msg=msg)
        self.assertEq(type(first), type(second))

    def test_decode_list_in_dict(self):
        d = utils.decode_form_data({
            'a_list':       ['foo', 'bar'],
            'a_list.42':    'baz',
            'a_list.23':    'meh'
        })
        self.assertEqual(d['a_list'], ['foo', 'bar', 'meh', 'baz'])

    def test_decode_form_data_multidicts(self):
        for dcls in WebObLikeDict, WerkzeugLikeDict:
            d = utils.decode_form_data(dcls())
            self.assertEqual(d['key1'], ['value1', 'value2', 'value3'])
            self.assertEqual(d['key2'], 'awesome')

    def test_escape(self):
        s1 = ('This string contains "<tags>" & "double-quotes", '
              'and single quotes "\'".')
        q1 = utils.Markup('This string contains &#34;&lt;tags&gt;&#34; &amp; '
                          '&#34;double-quotes&#34;, and single quotes '
                          '&#34;\'&#34;.')
        self.assertEqual(utils.escape(None), '')
        self.assertEqual(utils.escape(s1), q1)

        class HtmlAware(str):
            def __html__(self):
                return '<![CDATA[%s]]>' % self

        self.assertEqual(utils.escape(HtmlAware('xml & you')),
                                               '<![CDATA[xml & you]]>')
        self.assertRaises(TypeError, utils.escape)

    def test_make_name(self):
        self.assertEqual(utils.make_name(None, None), 'None')
        self.assertEqual(utils.make_name(None, ()), '()')
        self.assertEqual(utils.make_name((), None), '().None')
        self.assertEqual(utils.make_name(u'abc', u'def'), 'abc.def')
        self.assertEqual(utils.make_name(u'a\xef', u'd\xef'), u'a\xef.d\xef')
        self.assertEqual(utils.make_name('a\xef', 'd\xef'), 'a\xef.d\xef')
        self.assertRaises(UnicodeDecodeError, utils.make_name, '\xef', u'ef')

    def test_fill_dict(self):
        dic1 = {'foo': 'nothing', 'bar': 'nothing'}
        dic2 = dict(baz=u'moo', **dic1)
        self.assertEqual(utils.fill_dict(dic1), dic1)
        self.assertEqual(utils.fill_dict(None, **dic1), dic1)
        self.assertEqual(utils.fill_dict(dic1, bar=u'moo'), dic1)
        self.assertEqual(utils.fill_dict(dic1, baz=u'moo'), dic2)

    def test_set_fields(self):
        Object = type('Object', (), {})
        an_object = Object()
        dic1 = {'foo': 'Foo', 'bar': u'Bar'}
        utils.set_fields(an_object, dic1)
        self.assertEqual(an_object.__dict__, {})
        self.assertRaises(AttributeError, utils.set_fields,
                          an_object, dic1, 'bar')
        (an_object.foo, an_object.bar) = (None, None)
        self.assertEqual((an_object.foo, an_object.bar), (None, None))
        utils.set_fields(an_object, dic1, 'bar')
        self.assertEqual((an_object.foo, an_object.bar), (None, 'Bar'))
        utils.set_fields(an_object, dic1, *dic1.keys())
        self.assertEqual((an_object.foo, an_object.bar), ('Foo', 'Bar'))
        self.assertEqual(an_object.__dict__, dic1)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(UtilsTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
