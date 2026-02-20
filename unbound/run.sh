#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
set -e

bashio::log.info "Starting Unbound DNS resolver..."

CUSTOM_CONFIG_PATH="/addon_configs/unbound/unbound.conf"
BLOCKLISTS_FILE="/data/blocklists.json"
BLOCKLIST_CONF="/etc/unbound/blocklist.conf"
WHITELIST_FILE="/data/whitelist.json"
LOCAL_RECORDS_FILE="/data/local_records.json"
LOCAL_RECORDS_CONF="/etc/unbound/local_records.conf"

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

        if curl -sS --max-time 30 "${url}" 2>/dev/null | awk '
            BEGIN {
                skip["localhost"]=1; skip["localhost.localdomain"]=1
                skip["local"]=1; skip["broadcasthost"]=1
                skip["ip6-localhost"]=1; skip["ip6-loopback"]=1
                skip["ip6-localnet"]=1; skip["ip6-mcastprefix"]=1
                skip["ip6-allnodes"]=1; skip["ip6-allrouters"]=1
                skip["ip6-allhosts"]=1
            }
            {
                # Strip comments and carriage returns
                sub(/#.*/, ""); gsub(/\r/, "")
                if (NF < 2) next
                ip = $1; domain = tolower($2)
                if (ip != "0.0.0.0" && ip != "127.0.0.1") next
                if (domain in skip) next
                if (domain == "") next
                printf "local-zone: \"%s.\" always_refuse\n", domain
            }
        ' >> "${tmpfile}"; then
            :
        else
            bashio::log.warning "  Failed to download: ${url}"
        fi
    done

    # Sort and deduplicate
    sort -u "${tmpfile}" > "${BLOCKLIST_CONF}"
    rm -f "${tmpfile}"

    # Subtract whitelisted domains
    if [ -f "${WHITELIST_FILE}" ]; then
        local wl_count
        wl_count=$(jq '. | length' "${WHITELIST_FILE}")
        if [ "${wl_count}" != "0" ]; then
            local wl_tmpfile
            wl_tmpfile=$(mktemp)
            # Build a file of patterns to exclude (domain lines from whitelist)
            jq -r '.[]' "${WHITELIST_FILE}" | while IFS= read -r wl_domain; do
                # Match the exact local-zone line for this domain
                echo "local-zone: \"${wl_domain}.\" always_refuse"
            done > "${wl_tmpfile}"

            if [ -s "${wl_tmpfile}" ]; then
                grep -v -F -f "${wl_tmpfile}" "${BLOCKLIST_CONF}" > "${BLOCKLIST_CONF}.tmp" || true
                mv "${BLOCKLIST_CONF}.tmp" "${BLOCKLIST_CONF}"
                bashio::log.info "  Whitelist applied: removed $(wc -l < "${wl_tmpfile}") domain pattern(s)"
            fi
            rm -f "${wl_tmpfile}"
        fi
    fi

    local blocked
    blocked=$(wc -l < "${BLOCKLIST_CONF}")
    bashio::log.info "Blocklists applied: ${blocked} domains blocked"
}

# Initialize local records from addon config on first run
init_local_records() {
    if [ ! -f "${LOCAL_RECORDS_FILE}" ]; then
        # Seed from addon options if local_records is configured
        if bashio::config.has_value 'local_records'; then
            bashio::log.info "Seeding local records from addon config..."
            local records="[]"
            for record in $(bashio::jq '/data/options.json' '.local_records | keys[]'); do
                local hostname ip
                hostname=$(bashio::config "local_records[${record}].hostname")
                ip=$(bashio::config "local_records[${record}].ip")
                records=$(echo "${records}" | jq --arg h "${hostname}" --arg i "${ip}" '. + [{"hostname": $h, "ip": $i}]')
            done
            echo "${records}" > "${LOCAL_RECORDS_FILE}"
            bashio::log.info "Initialized local records from addon config"
        else
            echo "[]" > "${LOCAL_RECORDS_FILE}"
        fi
    fi

    # Write local_records.conf from JSON
    local rec_count
    rec_count=$(jq '. | length' "${LOCAL_RECORDS_FILE}")
    > "${LOCAL_RECORDS_CONF}"

    if [ "${rec_count}" != "0" ]; then
        bashio::log.info "Writing ${rec_count} local DNS record(s)..."
        for i in $(seq 0 $((rec_count - 1))); do
            local hostname ip
            hostname=$(jq -r ".[$i].hostname" "${LOCAL_RECORDS_FILE}")
            ip=$(jq -r ".[$i].ip" "${LOCAL_RECORDS_FILE}")
            bashio::log.info "  ${hostname} -> ${ip}"
            echo "local-zone: \"${hostname}.\" redirect" >> "${LOCAL_RECORDS_CONF}"
            echo "local-data: \"${hostname}. A ${ip}\"" >> "${LOCAL_RECORDS_CONF}"
        done
    fi
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

    # Set up query log file path
    LOG_FILE=""
    if [ "${LOG_QUERIES}" = "true" ]; then
        LOG_FILE="/data/unbound_queries.log"
        bashio::log.info "Query logging enabled: ${LOG_FILE}"

        # Log rotation: if log exceeds 50MB, rotate
        if [ -f "${LOG_FILE}" ]; then
            log_size=$(stat -f%z "${LOG_FILE}" 2>/dev/null || stat -c%s "${LOG_FILE}" 2>/dev/null || echo 0)
            if [ "${log_size}" -gt 52428800 ]; then
                bashio::log.info "Rotating query log (${log_size} bytes)..."
                mv "${LOG_FILE}" "${LOG_FILE}.old"
                : > "${LOG_FILE}"
            fi
        fi
    fi

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
    logfile: "${LOG_FILE}"
    log-queries: $(bool_to_yesno "$LOG_QUERIES")
    log-replies: $(bool_to_yesno "$LOG_QUERIES")
    log-servfail: yes

    # Include blocklist and local records
    include: "${BLOCKLIST_CONF}"
    include: "${LOCAL_RECORDS_CONF}"
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

# Initialize and apply blocklists, then local records
init_blocklists
apply_blocklists
init_local_records

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
