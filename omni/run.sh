#!/usr/bin/with-contenv bashio
# shellcheck shell=bash

# Trap errors and log them
trap 'bashio::log.error "Script failed at line $LINENO with exit code $?"' ERR
set -e

bashio::log.info "Starting Omni - Siderolabs Kubernetes Management Platform..."

# Read configuration from Home Assistant
NAME=$(bashio::config 'name')
ACCOUNT_ID=$(bashio::config 'account_id')
ADVERTISED_DOMAIN=$(bashio::config 'advertised_domain')
WIREGUARD_IP=$(bashio::config 'wireguard_advertised_ip')
TLS_CERT=$(bashio::config 'tls_cert')
TLS_KEY=$(bashio::config 'tls_key')

# Port settings
EVENT_SINK_PORT=$(bashio::config 'event_sink_port')
BIND_ADDR=$(bashio::config 'bind_addr')
SIDEROLINK_API_BIND_ADDR=$(bashio::config 'siderolink_api_bind_addr')
K8S_PROXY_BIND_ADDR=$(bashio::config 'k8s_proxy_bind_addr')
WIREGUARD_PORT=$(bashio::config 'wireguard_port')

# Authentication settings
AUTH_AUTH0_ENABLED=$(bashio::config 'auth_auth0_enabled')
AUTH_SAML_ENABLED=$(bashio::config 'auth_saml_enabled')
AUTH_OIDC_ENABLED=$(bashio::config 'auth_oidc_enabled')

# Check that at least one auth method is enabled (fail fast)
if [ "${AUTH_AUTH0_ENABLED}" != "true" ] && [ "${AUTH_SAML_ENABLED}" != "true" ] && [ "${AUTH_OIDC_ENABLED}" != "true" ]; then
    bashio::log.error "=========================================="
    bashio::log.error "NO AUTHENTICATION METHOD CONFIGURED!"
    bashio::log.error "=========================================="
    bashio::log.error "At least one authentication method must be enabled."
    bashio::log.error "Please enable one of the following in the add-on configuration:"
    bashio::log.error "  - auth_auth0_enabled: true (+ auth_auth0_domain and auth_auth0_client_id)"
    bashio::log.error "  - auth_saml_enabled: true (+ auth_saml_url)"
    bashio::log.error "  - auth_oidc_enabled: true (+ auth_oidc_provider_url and auth_oidc_client_id)"
    bashio::log.error "=========================================="
    exit 1
fi

# Validate required configuration
if [ -z "${ADVERTISED_DOMAIN}" ]; then
    bashio::log.error "advertised_domain is required!"
    exit 1
fi

if [ -z "${WIREGUARD_IP}" ]; then
    bashio::log.error "wireguard_advertised_ip is required!"
    exit 1
fi

# Generate account ID if not provided
if [ -z "${ACCOUNT_ID}" ]; then
    bashio::log.info "No account_id provided, generating one..."
    ACCOUNT_ID=$(cat /proc/sys/kernel/random/uuid)
    bashio::log.info "Generated account ID: ${ACCOUNT_ID}"
fi

# Handle GPG key - either from config (base64 encoded) or file
mkdir -p /data
PRIVATE_KEY_PATH="/data/omni.asc"

if bashio::config.has_value 'private_key_base64'; then
    bashio::log.info "Using GPG key from configuration (base64 encoded)..."
    bashio::config 'private_key_base64' | base64 -d > "${PRIVATE_KEY_PATH}" || {
        bashio::log.error "Failed to decode base64 GPG key"
        bashio::log.error "Make sure you encoded the key with: cat omni.asc | base64 -w 0"
        exit 1
    }
    bashio::log.info "GPG key saved to ${PRIVATE_KEY_PATH} ($(wc -c < "${PRIVATE_KEY_PATH}") bytes)"
    bashio::log.info "GPG key starts with: $(head -1 "${PRIVATE_KEY_PATH}")"
    bashio::log.info "GPG key ends with: $(tail -1 "${PRIVATE_KEY_PATH}")"
elif bashio::config.has_value 'private_key_file'; then
    PRIVATE_KEY_FILE=$(bashio::config 'private_key_file')
    if [ -f "/config/${PRIVATE_KEY_FILE}" ]; then
        bashio::log.info "Using GPG key from file: /config/${PRIVATE_KEY_FILE}"
        cp "/config/${PRIVATE_KEY_FILE}" "${PRIVATE_KEY_PATH}"
    else
        bashio::log.error "=========================================="
        bashio::log.error "GPG KEY FILE NOT FOUND!"
        bashio::log.error "=========================================="
        bashio::log.error "File not found: /config/${PRIVATE_KEY_FILE}"
        bashio::log.error "Either place your omni.asc file in the /config directory,"
        bashio::log.error "or use private_key_base64 with your base64-encoded key."
        bashio::log.error "To encode: cat omni.asc | base64 -w 0"
        bashio::log.error "=========================================="
        exit 1
    fi
else
    bashio::log.error "=========================================="
    bashio::log.error "NO GPG KEY CONFIGURED!"
    bashio::log.error "=========================================="
    bashio::log.error "Please configure one of the following:"
    bashio::log.error "  - private_key_base64: base64-encoded GPG key (single line)"
    bashio::log.error "    To encode: cat omni.asc | base64 -w 0"
    bashio::log.error "  - private_key_file: filename in /config directory"
    bashio::log.error "=========================================="
    exit 1
fi

# Strip port from WireGuard IP if user included it
WIREGUARD_IP_CLEAN="${WIREGUARD_IP%%:*}"

# Build command arguments
OMNI_ARGS=(
    "--account-id=${ACCOUNT_ID}"
    "--name=${NAME}"
    "--private-key-source=file://${PRIVATE_KEY_PATH}"
    "--event-sink-port=${EVENT_SINK_PORT}"
    "--bind-addr=${BIND_ADDR}"
    "--siderolink-api-bind-addr=${SIDEROLINK_API_BIND_ADDR}"
    "--k8s-proxy-bind-addr=${K8S_PROXY_BIND_ADDR}"
    "--advertised-api-url=https://${ADVERTISED_DOMAIN}/"
    "--siderolink-api-advertised-url=https://${ADVERTISED_DOMAIN}:8090/"
    "--siderolink-wireguard-advertised-addr=${WIREGUARD_IP_CLEAN}:${WIREGUARD_PORT}"
    "--advertised-kubernetes-proxy-url=https://${ADVERTISED_DOMAIN}:8100/"
)

# Add TLS certificates if provided
if [ -n "${TLS_CERT}" ] && [ -n "${TLS_KEY}" ]; then
    if [ -f "/ssl/${TLS_CERT}" ] && [ -f "/ssl/${TLS_KEY}" ]; then
        bashio::log.info "Using TLS certificates from /ssl"
        OMNI_ARGS+=(
            "--cert=/ssl/${TLS_CERT}"
            "--key=/ssl/${TLS_KEY}"
            "--siderolink-api-cert=/ssl/${TLS_CERT}"
            "--siderolink-api-key=/ssl/${TLS_KEY}"
        )
    else
        bashio::log.warning "TLS certificate files not found, running without TLS"
    fi
else
    bashio::log.warning "No TLS certificates configured, running in insecure mode"
fi

# Configure authentication - Auth0
if [ "${AUTH_AUTH0_ENABLED}" = "true" ]; then
    bashio::log.info "Configuring Auth0 authentication..."
    AUTH0_DOMAIN=$(bashio::config 'auth_auth0_domain')
    AUTH0_CLIENT_ID=$(bashio::config 'auth_auth0_client_id')
    
    if [ -z "${AUTH0_DOMAIN}" ] || [ -z "${AUTH0_CLIENT_ID}" ]; then
        bashio::log.error "Auth0 is enabled but domain or client_id is missing!"
        exit 1
    fi
    
    OMNI_ARGS+=(
        "--auth-auth0-enabled=true"
        "--auth-auth0-domain=${AUTH0_DOMAIN}"
        "--auth-auth0-client-id=${AUTH0_CLIENT_ID}"
    )
fi

# Configure authentication - SAML
if [ "${AUTH_SAML_ENABLED}" = "true" ]; then
    bashio::log.info "Configuring SAML authentication..."
    SAML_URL=$(bashio::config 'auth_saml_url')
    
    if [ -z "${SAML_URL}" ]; then
        bashio::log.error "SAML is enabled but URL is missing!"
        exit 1
    fi
    
    OMNI_ARGS+=(
        "--auth-saml-enabled=true"
        "--auth-saml-url=${SAML_URL}"
    )
fi

# Configure authentication - OIDC
if [ "${AUTH_OIDC_ENABLED}" = "true" ]; then
    bashio::log.info "Configuring OIDC authentication..."
    OIDC_PROVIDER_URL=$(bashio::config 'auth_oidc_provider_url')
    OIDC_CLIENT_ID=$(bashio::config 'auth_oidc_client_id')
    OIDC_CLIENT_SECRET=$(bashio::config 'auth_oidc_client_secret')
    OIDC_LOGOUT_URL=$(bashio::config 'auth_oidc_logout_url')
    
    if [ -z "${OIDC_PROVIDER_URL}" ] || [ -z "${OIDC_CLIENT_ID}" ]; then
        bashio::log.error "OIDC is enabled but provider_url or client_id is missing!"
        exit 1
    fi
    
    OMNI_ARGS+=(
        "--auth-oidc-enabled=true"
        "--auth-oidc-provider-url=${OIDC_PROVIDER_URL}"
        "--auth-oidc-client-id=${OIDC_CLIENT_ID}"
    )
    
    if [ -n "${OIDC_CLIENT_SECRET}" ]; then
        OMNI_ARGS+=("--auth-oidc-client-secret=${OIDC_CLIENT_SECRET}")
    fi
    
    if [ -n "${OIDC_LOGOUT_URL}" ]; then
        OMNI_ARGS+=("--auth-oidc-logout-url=${OIDC_LOGOUT_URL}")
    fi
    
    # Add OIDC scopes
    for scope in $(bashio::config 'auth_oidc_scopes'); do
        OMNI_ARGS+=("--auth-oidc-scopes=${scope}")
    done
fi

# Add initial users (for Auth0)
if bashio::config.has_value 'initial_users'; then
    for user in $(bashio::config 'initial_users'); do
        bashio::log.info "Adding initial user: ${user}"
        OMNI_ARGS+=("--initial-users=${user}")
    done
fi

# Create required directories in persistent storage
mkdir -p /share/omni/etcd
mkdir -p /share/omni/omnictl
ln -sf /share/omni/etcd /data/etcd 2>/dev/null || true

bashio::log.info "Starting Omni with configuration:"
bashio::log.info "  Name: ${NAME}"
bashio::log.info "  Account ID: ${ACCOUNT_ID}"
bashio::log.info "  Domain: ${ADVERTISED_DOMAIN}"
bashio::log.info "  WireGuard IP: ${WIREGUARD_IP}:${WIREGUARD_PORT}"

# Change to data directory for etcd storage
cd /share/omni

# Run Omni
exec /usr/local/bin/omni "${OMNI_ARGS[@]}"
