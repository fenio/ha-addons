ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install unbound, python/flask, and dependencies
RUN apk add --no-cache \
    unbound \
    bash \
    jq \
    curl \
    python3 \
    py3-flask \
    py3-waitress \
    openssl

# Create necessary directories and download root hints
RUN mkdir -p /var/run/unbound /etc/unbound /var/lib/unbound /data && \
    curl -o /etc/unbound/root.hints https://www.internic.net/domain/named.root && \
    unbound-anchor -a /var/lib/unbound/root.key || true && \
    chown -R unbound:unbound /var/lib/unbound /var/run/unbound

# Set up unbound-control keys for stats access
RUN unbound-control-setup

# Copy web application
COPY web/ /web/

# Copy run script
COPY run.sh /
RUN chmod a+x /run.sh

# Expose DNS ports and ingress port
EXPOSE 53/tcp 53/udp 2137

CMD ["/run.sh"]
