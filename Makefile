SHELL=/bin/bash

registry_acct=rtomac
image_name=gcalvault
image_tag=latest
image_version_tag="`cat VERSION | xargs`"
target_platforms=linux/amd64,linux/arm64,linux/arm/v7,linux/arm/v6

all: run

.PHONY: devenv
devenv:
	[ ! -d "./.devenv" ] && virtualenv .devenv || true
	. ./.devenv/bin/activate && pip install .

.PHONY: build
build:
	docker build \
		-t ${image_name}:local \
		.

user=foo.bar@gmail.com
.PHONY: run
run: build
	docker run -it --rm \
		-v ${PWD}/.conf:/root/.gcalvault \
		-v ${PWD}/.output:/root/gcalvault \
		${image_name}:local sync ${user}

.PHONY: test
test: build
	docker run -it --rm \
		-v ${PWD}/.conf:/root/.gcalvault \
		-v ${PWD}/.output:/root/gcalvault \
		--workdir /usr/local/src/gcalvault \
		--entrypoint pytest \
		${image_name}:local

.PHONY: debug
debug: build
	docker run -it --rm \
		-v ${PWD}/.conf:/root/.gcalvault \
		-v ${PWD}/.output:/root/gcalvault \
		-v ${PWD}:/usr/local/src/gcalvault \
		-v ${PWD}/src:/usr/local/lib/python3.8/site-packages/gcalvault \
		--entrypoint /bin/bash \
		${image_name}:local
