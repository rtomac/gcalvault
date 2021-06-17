SHELL=/bin/bash

pkg_version:=$(shell cat src/VERSION.txt | xargs)

container_hub_acct=rtomac
image_name=gcalvault
image_tag=latest
image_version_tag:=${pkg_version}
image_platforms=linux/amd64,linux/arm64,linux/arm/v7,linux/arm/v6

all: build

.PHONY: devenv
devenv:
	[ ! -d "./.devenv" ] && virtualenv .devenv || true
	. ./.devenv/bin/activate && pip install '.[test,release]'

.PHONY: dist
dist:
	python3 setup.py sdist
	ln -f "dist/gcalvault-${pkg_version}.tar.gz" "dist/gcalvault-latest.tar.gz"

.PHONY: build
build: dist
	docker build \
		-t ${image_name}:local \
		.

.PHONY: test
test: build
	docker run -it --rm \
		-v ${PWD}/.conf:/root/.gcalvault \
		-v ${PWD}/.output:/root/gcalvault \
		-v ${PWD}:/usr/local/src/gcalvault \
		--workdir /usr/local/src/gcalvault \
		--entrypoint pytest \
		${image_name}:local

.PHONY: debug
debug: build
	docker run -it --rm \
		-v ${PWD}/.conf:/root/.gcalvault \
		-v ${PWD}/.output:/root/gcalvault \
		-v ${PWD}/bin/gcalvault:/usr/local/bin/gcalvault \
		-v ${PWD}/src:/usr/local/lib/python3.8/site-packages/gcalvault \
		-v ${PWD}/tests:/usr/local/src/gcalvault/tests \
		--entrypoint /bin/bash \
		${image_name}:local

user=foo.bar@gmail.com
.PHONY: run
run: build
	docker run -it --rm \
		-v ${PWD}/.conf:/root/.gcalvault \
		-v ${PWD}/.output:/root/gcalvault \
		${image_name}:local sync ${user}

.PHONY: release
release: test
	twine upload --repository testpypi dist/gcalvault-${pkg_version}.tar.gz
	
	twine upload dist/gcalvault-${pkg_version}.tar.gz

	docker buildx build \
		--tag "${container_hub_acct}/${image_name}:${image_tag}" \
		--tag "${container_hub_acct}/${image_name}:${image_version_tag}" \
		--platform "${image_platforms}" \
		--push \
		.
