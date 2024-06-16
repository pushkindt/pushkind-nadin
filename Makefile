.PHONY: run setup deploy_dev deploy_prod upgrade

run:
	poetry run flask run

setup:
	poetry run flask db init
	poetry run flask db migrate
	poetry run flask db upgrade

deploy_dev:
	git pull origin dev
	poetry run flask db migrate
	poetry run flask db upgrade
	supervisorctl restart nadin_dev

deploy_prod:
	git pull origin main
	poetry run flask db migrate
	poetry run flask db upgrade
	supervisorctl restart nadin_prod

upgrade:
	poetry run flask db migrate
	poetry run flask db upgrade

icu: libsqliteicu.so
	gcc -shared icu.c -g -o libsqliteicu.so -fPIC `pkg-config --libs --cflags icu-uc icu-io`
