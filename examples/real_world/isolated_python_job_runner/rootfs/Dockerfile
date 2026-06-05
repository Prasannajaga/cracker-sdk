FROM fedora:40

COPY init /init
COPY agent.py /agent.py

RUN dnf install -y python3 nodejs npm golang rust cargo gcc util-linux procps-ng \
    && npm install -g typescript \
    && ln -sf "$(command -v tsc)" /usr/bin/tsc \
    && dnf clean all \
    && chmod +x /init
