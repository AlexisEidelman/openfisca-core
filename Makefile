TESTS_DIR=openfisca_core/tests

all: flake8 test

check-syntax-errors:
	@# This is a hack around flake8 not displaying E910 errors with the select option.
	@# Do not analyse .gitignored files.
	@# `make` needs `$$` to output `$`. Ref: http://stackoverflow.com/questions/2382764.
	test -z "`flake8 --first $(shell git ls-files | grep "\.py$$") | grep E901`"

clean-pyc:
	find . -name '*.pyc' -exec rm \{\} \;

ctags:
	ctags --recurse=yes .

flake8: clean-pyc
	flake8

test: check-syntax-errors
	nosetests $(TESTS_DIR) --stop --with-doctest

test-ci: check-syntax-errors
	nosetests $(TESTS_DIR) --with-doctest

test-with-coverage:
	nosetests $(TESTS_DIR) --stop --with-coverage --cover-package=openfisca_core --cover-erase --cover-branches --cover-html
