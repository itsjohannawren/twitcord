FROM debian:12-slim

RUN \
	apt update && \
	apt install -y python3-virtualenv && \
	mkdir /app

COPY * /app/

RUN \
	cd /app && \
	virtualenv . && \
	. bin/activate && \
	pip install -r requirements.txt && \
	playwright install && \
	playwright install-deps && \
	touch config.yaml history.json state.json

VOLUME /app/config.yaml
VOLUME /app/history.json
VOLUME /app/state.json

WORKDIR /app
ENTRYPOINT /app/app.py
