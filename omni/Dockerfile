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
ARG OMNI_VERSION=v1.12.3
ARG OMNI_SHA256_AMD64=b425976e336f711d9644c731bd731716e145caa709f146ac36885ec5513cba1d
ARG OMNI_SHA256_ARM64=e1baecdcb614a6db4607d4ecd993427923e8b5bea7d2c0655a9f38434547204d
ARG TARGETARCH

# Download and install Omni binary
RUN case "${TARGETARCH}" in \
        "amd64") ARCH="amd64"; SHA256="${OMNI_SHA256_AMD64}" ;; \
        "arm64") ARCH="arm64"; SHA256="${OMNI_SHA256_ARM64}" ;; \
        *) echo "Unsupported architecture: ${TARGETARCH}" && exit 1 ;; \
    esac && \
    curl -fsSL -o /usr/local/bin/omni \
        "https://github.com/siderolabs/omni/releases/download/${OMNI_VERSION}/omni-linux-${ARCH}" && \
    echo "${SHA256}  /usr/local/bin/omni" | sha256sum -c - && \
    chmod +x /usr/local/bin/omni

# Create config directory
RUN mkdir -p /config

# Copy run script
COPY run.sh /
RUN chmod a+x /run.sh

# Expose ports
EXPOSE 443/tcp 8090/tcp 8091/tcp 8100/tcp 50180/udp

CMD ["/run.sh"]
