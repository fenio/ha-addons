#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
set -e

bashio::log.level "$(bashio::config 'log_level')"
bashio::log.info "Starting Unbound DNS resolver ($(bashio::addon.version))..."

bashio::log.debug "HOSTNAME: ${HOSTNAME}"
bashio::log.debug "Contents of /addon_configs/:"
ls -la /addon_configs/ >&2 || true

# Detect addon config directory: try both hyphen and underscore variants
ADDON_DIR=""
for candidate in "/addon_configs/${HOSTNAME}" "/addon_configs/${HOSTNAME//-/_}"; do
    if [ -d "${candidate}" ]; then
        ADDON_DIR="${candidate}"
        break
    fi
done
# Fallback: find any directory matching *unbound*
if [ -z "${ADDON_DIR}" ]; then
    ADDON_DIR=$(find /addon_configs/ -maxdepth 1 -type d -name "*unbound*" 2>/dev/null | head -1)
fi
if [ -n "${ADDON_DIR}" ]; then
    CUSTOM_CONFIG_PATH="${ADDON_DIR}/unbound.conf"
else
    CUSTOM_CONFIG_PATH="/addon_configs/${HOSTNAME}/unbound.conf"
fi
bashio::log.debug "Addon config dir: ${ADDON_DIR:-not found}"
bashio::log.debug "Custom config path: ${CUSTOM_CONFIG_PATH}"
BLOCKLISTS_FILE="/data/blocklists.json"
BLOCKLIST_CONF="/etc/unbound/blocklist.conf"
WHITELIST_FILE="/data/whitelist.json"
LOCAL_RECORDS_FILE="/data/local_records.json"
LOCAL_RECORDS_CONF="/etc/unbound/local_records.conf"

# Initialize blocklists file if it doesn't exist
init_blocklists() {
    if [ ! -f "${BLOCKLISTS_FILE}" ]; then
        echo "[]" > "${BLOCKLISTS_FILE}"
        bashio::log.info "Initialized empty blocklists file"
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

# Initialize local records file if it doesn't exist
init_local_records() {
    if [ ! -f "${LOCAL_RECORDS_FILE}" ]; then
        echo "[]" > "${LOCAL_RECORDS_FILE}"
        bashio::log.info "Initialized empty local records file"
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

# Update root hints (fallback to bundled copy on failure)
bashio::log.info "Updating root hints..."
if curl -sS --max-time 15 -o /etc/unbound/root.hints.tmp \
    https://www.internic.net/domain/named.root 2>/dev/null; then
    mv /etc/unbound/root.hints.tmp /etc/unbound/root.hints
    bashio::log.info "Root hints updated"
else
    rm -f /etc/unbound/root.hints.tmp
    bashio::log.warning "Failed to update root hints, using bundled copy"
fi

# Seed config.json from options.json on first run
python3 /web/config_gen.py --seed-if-needed

# Check custom_config from config.json
if jq -e '.custom_config == true' /data/config.json >/dev/null 2>&1; then
    # Custom config mode: use user-provided unbound.conf
    bashio::log.info "Custom config mode enabled"

    if [ ! -f "${CUSTOM_CONFIG_PATH}" ]; then
        bashio::log.error "Custom config enabled but ${CUSTOM_CONFIG_PATH} not found!"
        bashio::log.error "Place your unbound.conf in the addon_configs/${ADDON_SLUG}/ directory."
        exit 1
    fi

    bashio::log.info "Using custom config from ${CUSTOM_CONFIG_PATH}"
    cp "${CUSTOM_CONFIG_PATH}" /etc/unbound/unbound.conf
else
    # Generated config mode
    bashio::log.info "Generating Unbound configuration..."
    python3 /web/config_gen.py --generate
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

# Start web UI in background
bashio::log.info "Starting web UI on port 2137..."
INGRESS_PATH=$(bashio::addon.ingress_entry) \
    python3 /web/app.py &

# Run unbound in foreground
exec unbound -d -c /etc/unbound/unbound.conf
