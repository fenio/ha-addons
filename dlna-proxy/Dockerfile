# Global ARG for build base image
ARG BUILD_FROM

# Get dlna-proxy binary from the official image
FROM ghcr.io/fenio/dlna-proxy:0.6.0 AS dlna-proxy

# Build the actual addon
FROM ${BUILD_FROM}

# Install required dependencies
RUN apk add --no-cache \
    bash \
    jq

# Copy dlna-proxy binary from the official image
COPY --from=dlna-proxy /dlna-proxy /usr/local/bin/dlna-proxy

# Copy run script
COPY run.sh /
RUN chmod a+x /run.sh

CMD ["/run.sh"]
