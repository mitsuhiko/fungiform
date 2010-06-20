#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Fungiform
    ~~~~~~~~~

    :copyright: (c) 2009 by Armin Ronacher, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


setup(
    name = 'Fungiform',
    version = '0.1',
    url = 'http://github.com/mitsuhiko/fungiform',
    license = 'BSD License',
    author = 'Armin Ronacher',
    author_email = 'armin.ronacher@active-4.com',
    description = 'form library',
    long_description = __doc__,
    keywords = 'form library',
    packages = ['fungiform', 'fungiform.tests'],
    platforms = 'any',
    zip_safe = False,
    test_suite = 'fungiform.tests.suite',
    include_package_data = True,
    classifiers = [
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Development Status :: 4 - Beta'
    ],
)
