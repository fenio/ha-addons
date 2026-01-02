ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install required dependencies
RUN apk add --no-cache \
    bash \
    jq \
    curl \
    gnupg \
    iptables \
    wireguard-tools

# Set Omni version - update this when new versions are released
ARG OMNI_VERSION=v1.4.6
ARG TARGETARCH

# Download and install Omni binary
RUN case "${TARGETARCH}" in \
        "amd64") ARCH="amd64" ;; \
        "arm64") ARCH="arm64" ;; \
        *) echo "Unsupported architecture: ${TARGETARCH}" && exit 1 ;; \
    esac && \
    curl -fsSL -o /usr/local/bin/omni \
        "https://github.com/siderolabs/omni/releases/download/${OMNI_VERSION}/omni-linux-${ARCH}" && \
    chmod +x /usr/local/bin/omni

# Create directories for persistent data
RUN mkdir -p /data/etcd /config

# Copy run script
COPY run.sh /
RUN chmod a+x /run.sh

# Expose ports
EXPOSE 443/tcp 8090/tcp 8091/tcp 8100/tcp 50180/udp

CMD ["/run.sh"]
