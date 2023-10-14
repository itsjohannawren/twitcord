GIT_TAG := $(shell git describe --tags 2>/dev/null || echo "dev")

build:
	docker build -t "twitcord:$(GIT_TAG)" .

.PHONY: build
