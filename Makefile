.PHONY: run

run:
	poetry run flask run

icu: libsqliteicu.so
	gcc -shared icu.c -g -o libsqliteicu.so -fPIC `pkg-config --libs --cflags icu-uc icu-io`
