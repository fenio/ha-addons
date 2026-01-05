# Get dlnaproxy binary from the official image
FROM ghcr.io/fenio/dlnaproxy:main AS dlnaproxy

# Build the actual addon
ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install required dependencies
RUN apk add --no-cache \
    bash \
    jq

# Copy dlnaproxy binary from the official image
COPY --from=dlnaproxy /dlnaproxy /usr/local/bin/dlnaproxy

# Copy run script
COPY run.sh /
RUN chmod a+x /run.sh

CMD ["/run.sh"]
