FROM python:3.9-alpine

RUN apk add --no-cache bash git

COPY dist/gcalvault-latest.tar.gz /usr/local/src/

RUN cd /usr/local/src \
    && pip install gcalvault-latest.tar.gz[test] \
    && mkdir -p /root/gcalvault

WORKDIR /root/gcalvault
ENTRYPOINT [ "gcalvault" ]
