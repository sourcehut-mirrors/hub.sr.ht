SRHT_PATH?=/usr/lib/python3.10/site-packages/srht
MODULE=hubsrht/
include ${SRHT_PATH}/Makefile

all: api

api:
	cd api && go generate ./graph
	cd api && go build

.PHONY: all api
