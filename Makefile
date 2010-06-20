.PHONY: clean-pyc test

all: clean-pyc test

test:
	python setup.py test

release:
	python setup.py release sdist upload

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
