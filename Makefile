.PHONY: run setup

run:
	poetry run flask run

setup:
	poetry run flask db init
	poetry run flask db migrate
	poetry run flask db upgrade

icu: libsqliteicu.so
	gcc -shared icu.c -g -o libsqliteicu.so -fPIC `pkg-config --libs --cflags icu-uc icu-io`
