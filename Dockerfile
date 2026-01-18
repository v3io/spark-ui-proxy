FROM python:3.13-alpine

COPY ./spark-ui-proxy.py /

ENV SERVER_PORT=80
ENV BIND_ADDR="0.0.0.0"

EXPOSE 80

# to upgrade sqlite to 3.49.2-r1, in order to get the fix for CVE-2025-6965
RUN apk update && apk add --no-cache sqlite sqlite-libs && apk info -e sqlite sqlite-libs

ENTRYPOINT ["python", "/spark-ui-proxy.py"]
