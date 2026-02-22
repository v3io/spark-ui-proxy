SPARK_UI_PROXY_TAG ?= 0.2.6
SPARK_UI_PROXY_REPOSITORY ?= gcr.io/iguazio/
DOCKER_DEFAULT_PLATFORM ?= linux/amd64

.PHONY: build
build:
	docker build --platform=$(DOCKER_DEFAULT_PLATFORM) --no-cache --progress=plain --tag=$(SPARK_UI_PROXY_REPOSITORY)spark-ui-proxy:$(SPARK_UI_PROXY_TAG) .
