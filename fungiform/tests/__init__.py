# -*- coding: utf-8 -*-
"""
    fungiform.tests
    ~~~~~~~~~~~~~~~

    The fungiform test suite.

    :copyright: (c) 2010 by the Fungiform Team.
    :license: BSD, see LICENSE for more details.
"""
import doctest
import unittest


def suite():
    from fungiform.tests import forms, utils, widgets
    pkg_prefix = ''.join(__name__.rpartition('.')[:-1])

    def DocTestSuite(name):
        return doctest.DocTestSuite(pkg_prefix + name)

    suite = unittest.TestSuite()
    suite.addTest(forms.suite())
    suite.addTest(utils.suite())
    suite.addTest(widgets.suite())
    suite.addTest(DocTestSuite('forms'))
    suite.addTest(DocTestSuite('redirects'))
    suite.addTest(DocTestSuite('utils'))
    suite.addTest(DocTestSuite('widgets'))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
