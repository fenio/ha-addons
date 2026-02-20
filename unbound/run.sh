#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
set -e

bashio::log.info "Starting Unbound DNS resolver..."

CUSTOM_CONFIG_PATH="/addon_configs/unbound/unbound.conf"
BLOCKLISTS_FILE="/data/blocklists.json"
BLOCKLIST_CONF="/etc/unbound/blocklist.conf"

# Initialize blocklists file from addon config if it doesn't exist
init_blocklists() {
    if [ ! -f "${BLOCKLISTS_FILE}" ]; then
        # Seed from addon options
        local urls
        urls=$(bashio::jq '/data/options.json' '.blocklists // []')
        echo "${urls}" > "${BLOCKLISTS_FILE}"
        bashio::log.info "Initialized blocklists from addon config"
    fi
}

# Download and apply blocklists
apply_blocklists() {
    bashio::log.info "Processing blocklists..."

    if [ ! -f "${BLOCKLISTS_FILE}" ]; then
        # No blocklists configured, write empty conf
        > "${BLOCKLIST_CONF}"
        return
    fi

    local count
    count=$(jq '. | length' "${BLOCKLISTS_FILE}")
    if [ "${count}" = "0" ]; then
        bashio::log.info "No blocklists configured"
        > "${BLOCKLIST_CONF}"
        return
    fi

    local tmpfile
    tmpfile=$(mktemp)

    for i in $(seq 0 $((count - 1))); do
        local url
        url=$(jq -r ".[$i]" "${BLOCKLISTS_FILE}")
        bashio::log.info "  Downloading blocklist: ${url}"

        local raw
        if raw=$(curl -sS --max-time 30 "${url}" 2>/dev/null); then
            # Parse hosts-format file and convert to unbound local-zone directives
            echo "${raw}" | while IFS= read -r line; do
                # Skip comments and empty lines
                line=$(echo "${line}" | sed 's/#.*//' | tr -d '\r')
                [ -z "${line}" ] && continue

                # Parse hosts format: 0.0.0.0 domain or 127.0.0.1 domain
                local ip domain
                ip=$(echo "${line}" | awk '{print $1}')
                domain=$(echo "${line}" | awk '{print $2}')

                [ -z "${domain}" ] && continue

                # Only process blocking entries
                case "${ip}" in
                    0.0.0.0|127.0.0.1) ;;
                    *) continue ;;
                esac

                # Skip common local hostnames
                case "${domain}" in
                    localhost|localhost.localdomain|local|broadcasthost) continue ;;
                    ip6-localhost|ip6-loopback|ip6-localnet) continue ;;
                    ip6-mcastprefix|ip6-allnodes|ip6-allrouters|ip6-allhosts) continue ;;
                esac

                echo "local-zone: \"${domain}.\" always_refuse"
            done >> "${tmpfile}"
        else
            bashio::log.warning "  Failed to download: ${url}"
        fi
    done

    # Sort and deduplicate
    sort -u "${tmpfile}" > "${BLOCKLIST_CONF}"
    rm -f "${tmpfile}"

    local blocked
    blocked=$(wc -l < "${BLOCKLIST_CONF}")
    bashio::log.info "Blocklists applied: ${blocked} domains blocked"
}

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

    # Include blocklist
    include: "${BLOCKLIST_CONF}"
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

    # Add remote-control section for unbound-control access
    cat >> /etc/unbound/unbound.conf << EOF

remote-control:
    control-enable: yes
    control-interface: 127.0.0.1
    server-key-file: "/etc/unbound/unbound_server.key"
    server-cert-file: "/etc/unbound/unbound_server.pem"
    control-key-file: "/etc/unbound/unbound_control.key"
    control-cert-file: "/etc/unbound/unbound_control.pem"
EOF

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

# Initialize and apply blocklists
init_blocklists
apply_blocklists

# Validate configuration
bashio::log.info "Validating Unbound configuration..."
if ! unbound-checkconf /etc/unbound/unbound.conf; then
    bashio::log.error "Invalid Unbound configuration!"
    bashio::log.error "Generated config:"
    cat /etc/unbound/unbound.conf
    exit 1
fi

bashio::log.info "Configuration valid. Starting Unbound..."

# Start Flask web UI in background
bashio::log.info "Starting web UI on port 2137..."
INGRESS_PATH=$(bashio::addon.ingress_entry) \
    python3 /web/app.py &

# Run unbound in foreground
exec unbound -d -c /etc/unbound/unbound.conf
