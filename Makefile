SPARK_UI_PROXY_TAG ?= latest
SPARK_UI_PROXY_REPOSITORY ?= v3io/

.PHONY: build
build:
	docker build --tag=$(SPARK_UI_PROXY_REPOSITORY)spark-ui-proxy:$(SPARK_UI_PROXY_TAG) .
