ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install unbound and dependencies
RUN apk add --no-cache \
    unbound \
    unbound-libs \
    dnssec-root \
    bash \
    jq \
    curl

# Create necessary directories
RUN mkdir -p /var/run/unbound && \
    chown unbound:unbound /var/run/unbound

# Copy root hints for recursive resolution
RUN curl -o /etc/unbound/root.hints https://www.internic.net/domain/named.root

# Copy configuration files
COPY rootfs /

# Copy run script
COPY run.sh /
RUN chmod a+x /run.sh

# Expose DNS ports
EXPOSE 53/tcp 53/udp

CMD ["/run.sh"]
