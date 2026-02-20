#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
set -e

bashio::log.info "Starting Unbound DNS resolver..."

CUSTOM_CONFIG_PATH="/addon_configs/unbound/unbound.conf"

if bashio::config.true 'custom_config'; then
    # Custom config mode: use user-provided unbound.conf
    bashio::log.info "Custom config mode enabled"

    if [ ! -f "${CUSTOM_CONFIG_PATH}" ]; then
        bashio::log.error "Custom config enabled but ${CUSTOM_CONFIG_PATH} not found!"
        bashio::log.error "Place your unbound.conf in the addon_configs/unbound/ directory."
        exit 1
    fi

    bashio::log.info "Using custom config from ${CUSTOM_CONFIG_PATH}"
    cp "${CUSTOM_CONFIG_PATH}" /etc/unbound/unbound.conf
else
    # Generated config mode: build config from addon options

    # Read configuration from Home Assistant
    NUM_THREADS=$(bashio::config 'num_threads')
    PREFETCH=$(bashio::config 'prefetch')
    FAST_SERVER_PERMIL=$(bashio::config 'fast_server_permil')
    FAST_SERVER_NUM=$(bashio::config 'fast_server_num')
    PREFER_IP4=$(bashio::config 'prefer_ip4')
    DO_IP4=$(bashio::config 'do_ip4')
    DO_IP6=$(bashio::config 'do_ip6')
    CACHE_MIN_TTL=$(bashio::config 'cache_min_ttl')
    CACHE_MAX_TTL=$(bashio::config 'cache_max_ttl')
    ENABLE_DNSSEC=$(bashio::config 'enable_dnssec')
    QNAME_MINIMISATION=$(bashio::config 'qname_minimisation')
    HIDE_IDENTITY=$(bashio::config 'hide_identity')
    HIDE_VERSION=$(bashio::config 'hide_version')
    VERBOSITY=$(bashio::config 'verbosity')
    LOG_QUERIES=$(bashio::config 'log_queries')

    # Convert booleans to yes/no
    bool_to_yesno() {
        if [ "$1" = "true" ]; then
            echo "yes"
        else
            echo "no"
        fi
    }

    # Generate unbound configuration
    cat > /etc/unbound/unbound.conf << EOF
server:
    # Daemon settings
    do-daemonize: no
    chroot: ""

    # Network settings
    interface: 0.0.0.0
    port: 53
    do-ip4: $(bool_to_yesno "$DO_IP4")
    do-ip6: $(bool_to_yesno "$DO_IP6")
    prefer-ip4: $(bool_to_yesno "$PREFER_IP4")
    do-udp: yes
    do-tcp: yes
    do-not-query-localhost: no

    # Performance settings
    num-threads: ${NUM_THREADS}
    prefetch: $(bool_to_yesno "$PREFETCH")
    fast-server-permil: ${FAST_SERVER_PERMIL}
    fast-server-num: ${FAST_SERVER_NUM}
    msg-cache-slabs: 4
    rrset-cache-slabs: 4
    infra-cache-slabs: 4
    key-cache-slabs: 4

    # Cache settings
    cache-min-ttl: ${CACHE_MIN_TTL}
    cache-max-ttl: ${CACHE_MAX_TTL}

    # Privacy settings
    qname-minimisation: $(bool_to_yesno "$QNAME_MINIMISATION")
    hide-identity: $(bool_to_yesno "$HIDE_IDENTITY")
    hide-version: $(bool_to_yesno "$HIDE_VERSION")

    # Root hints for recursive resolution
    root-hints: "/etc/unbound/root.hints"

    # Trust anchor for DNSSEC
    auto-trust-anchor-file: "/var/lib/unbound/root.key"

    # Hardening
    harden-glue: yes
    harden-dnssec-stripped: yes
    harden-referral-path: yes

    # Log settings
    verbosity: ${VERBOSITY}
    logfile: ""
    log-queries: $(bool_to_yesno "$LOG_QUERIES")
    log-replies: $(bool_to_yesno "$LOG_QUERIES")
    log-servfail: yes
EOF

    # Add access control entries
    bashio::log.info "Configuring access control..."
    for network in $(bashio::config 'access_control'); do
        bashio::log.info "  Allowing network: ${network}"
        echo "    access-control: ${network} allow" >> /etc/unbound/unbound.conf
    done

    # Add DNSSEC configuration
    if [ "${ENABLE_DNSSEC}" = "true" ]; then
        bashio::log.info "DNSSEC validation enabled"
        cat >> /etc/unbound/unbound.conf << EOF

    # DNSSEC validation
    val-clean-additional: yes
EOF
    else
        bashio::log.info "DNSSEC validation disabled"
        cat >> /etc/unbound/unbound.conf << EOF

    # DNSSEC validation disabled
    module-config: "iterator"
EOF
    fi

    # Add local DNS records
    if bashio::config.has_value 'local_records'; then
        bashio::log.info "Configuring local DNS records..."
        echo "" >> /etc/unbound/unbound.conf
        echo "    # Local DNS records" >> /etc/unbound/unbound.conf

        for record in $(bashio::jq '/data/options.json' '.local_records | keys[]'); do
            hostname=$(bashio::config "local_records[${record}].hostname")
            ip=$(bashio::config "local_records[${record}].ip")
            bashio::log.info "  ${hostname} -> ${ip}"
            echo "    local-zone: \"${hostname}.\" redirect" >> /etc/unbound/unbound.conf
            echo "    local-data: \"${hostname}. A ${ip}\"" >> /etc/unbound/unbound.conf
        done
    fi

    # Add forward zone configuration if forward servers are specified
    if bashio::config.has_value 'forward_servers'; then
        bashio::log.info "Configuring forward servers (forwarding mode)..."
        cat >> /etc/unbound/unbound.conf << EOF

forward-zone:
    name: "."
    forward-tls-upstream: no
EOF

        for server in $(bashio::config 'forward_servers'); do
            bashio::log.info "  Forward server: ${server}"
            echo "    forward-addr: ${server}" >> /etc/unbound/unbound.conf
        done
    else
        bashio::log.info "No forward servers configured (recursive resolver mode)"
    fi
fi

# Validate configuration
bashio::log.info "Validating Unbound configuration..."
if ! unbound-checkconf /etc/unbound/unbound.conf; then
    bashio::log.error "Invalid Unbound configuration!"
    bashio::log.error "Generated config:"
    cat /etc/unbound/unbound.conf
    exit 1
fi

bashio::log.info "Configuration valid. Starting Unbound..."

# Run unbound in foreground
exec unbound -d -c /etc/unbound/unbound.conf
