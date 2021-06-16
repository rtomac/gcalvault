FROM python:3

COPY setup.py /usr/local/src/gcalvault/
COPY bin /usr/local/src/gcalvault/bin
COPY src /usr/local/src/gcalvault/src
COPY tests /usr/local/src/gcalvault/tests
RUN cd /usr/local/src/gcalvault \
    && pip install . \
    && mkdir -p /root/gcalvault

WORKDIR /root/gcalvault
ENTRYPOINT [ "gcalvault" ]
