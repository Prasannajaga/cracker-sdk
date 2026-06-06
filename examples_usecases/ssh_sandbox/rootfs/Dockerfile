FROM alpine:3.20

COPY init /init
COPY seed_entropy.c /seed_entropy.c

RUN apk add --no-cache openssh-server iproute2 \
    && apk add --no-cache --virtual .build-deps gcc musl-dev linux-headers \
    && gcc -Os -s -Wall -Wextra -o /usr/local/sbin/seed-entropy /seed_entropy.c \
    && apk del .build-deps \
    && rm -f /seed_entropy.c \
    && mkdir -p /run/sshd /root/.ssh \
    && chmod 700 /root/.ssh \
    && chmod +x /init \
    && ssh-keygen -A \
    && sed -i 's/^#PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config \
    && sed -i 's/^#PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config \
    && printf '%s\n' \
        'AddressFamily inet' \
        'ListenAddress 0.0.0.0' \
        'UseDNS no' \
        'PidFile /run/sshd.pid' \
        >> /etc/ssh/sshd_config

COPY authorized_keys.example /root/.ssh/authorized_keys

RUN chmod 700 /root/.ssh \
    && chmod 600 /root/.ssh/authorized_keys \
    && test -s /etc/ssh/ssh_host_ed25519_key
