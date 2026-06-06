FROM alpine:3.20

COPY agent.c /agent.c

RUN apk add --no-cache bash build-base go linux-headers python3 quickjs \
    && gcc -static -Os -s -Wall -Wextra -o /init /agent.c \
    && chmod +x /init \
    && mkdir -p /workspace
