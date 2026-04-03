#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
set -e

bashio::log.info "Starting Omni - Siderolabs Kubernetes Management Platform..."

# Read configuration from Home Assistant
NAME=$(bashio::config 'name')
ACCOUNT_ID=$(bashio::config 'account_id' || true)
ADVERTISED_DOMAIN=$(bashio::config 'advertised_domain')
WIREGUARD_IP=$(bashio::config 'wireguard_advertised_ip')
TLS_CERT=$(bashio::config 'tls_cert' || true)
TLS_KEY=$(bashio::config 'tls_key' || true)

# Port settings
EVENT_SINK_PORT=$(bashio::config 'event_sink_port')
BIND_ADDR=$(bashio::config 'bind_addr')
MACHINE_API_BIND_ADDR=$(bashio::config 'siderolink_api_bind_addr')
K8S_PROXY_BIND_ADDR=$(bashio::config 'k8s_proxy_bind_addr')
WIREGUARD_PORT=$(bashio::config 'wireguard_port')

# Authentication settings
AUTH_AUTH0_ENABLED=$(bashio::config 'auth_auth0_enabled' || true)
AUTH_SAML_ENABLED=$(bashio::config 'auth_saml_enabled' || true)
AUTH_OIDC_ENABLED=$(bashio::config 'auth_oidc_enabled' || true)

# Check that at least one auth method is enabled
if [ "${AUTH_AUTH0_ENABLED}" != "true" ] && [ "${AUTH_SAML_ENABLED}" != "true" ] && [ "${AUTH_OIDC_ENABLED}" != "true" ]; then
    bashio::log.error "No authentication method configured!"
    bashio::log.error "Enable one of: auth_auth0_enabled, auth_saml_enabled, or auth_oidc_enabled"
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

# Generate account ID if not provided, persist it for subsequent starts
ACCOUNT_ID_FILE="/share/omni/account-id"
if [ -z "${ACCOUNT_ID}" ]; then
    if [ -f "${ACCOUNT_ID_FILE}" ]; then
        ACCOUNT_ID=$(cat "${ACCOUNT_ID_FILE}")
        bashio::log.info "Using persisted account ID: ${ACCOUNT_ID}"
    else
        ACCOUNT_ID=$(cat /proc/sys/kernel/random/uuid)
        mkdir -p /share/omni
        echo "${ACCOUNT_ID}" > "${ACCOUNT_ID_FILE}"
        bashio::log.info "Generated and persisted account ID: ${ACCOUNT_ID}"
    fi
fi

# Handle GPG key - either from config (base64 encoded) or file
mkdir -p /data
PRIVATE_KEY_PATH="/data/omni.asc"

if bashio::config.has_value 'private_key_base64'; then
    bashio::log.info "Using GPG key from configuration (base64 encoded)..."
    bashio::config 'private_key_base64' | base64 -d > "${PRIVATE_KEY_PATH}" || {
        bashio::log.error "Failed to decode base64 GPG key"
        exit 1
    }
elif bashio::config.has_value 'private_key_file'; then
    PRIVATE_KEY_FILE=$(bashio::config 'private_key_file')
    if [ -f "/config/${PRIVATE_KEY_FILE}" ]; then
        bashio::log.info "Using GPG key from file: /config/${PRIVATE_KEY_FILE}"
        cp "/config/${PRIVATE_KEY_FILE}" "${PRIVATE_KEY_PATH}"
    else
        bashio::log.error "GPG key file not found: /config/${PRIVATE_KEY_FILE}"
        exit 1
    fi
else
    bashio::log.error "No GPG key configured! Set private_key_base64 or private_key_file"
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
    "--machine-api-bind-addr=${MACHINE_API_BIND_ADDR}"
    "--k8s-proxy-bind-addr=${K8S_PROXY_BIND_ADDR}"
    "--sqlite-storage-path=/_out/secondary-storage/sqlite.db"
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
            "--machine-api-cert=/ssl/${TLS_CERT}"
            "--machine-api-key=/ssl/${TLS_KEY}"
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
    AUTH0_DOMAIN=$(bashio::config 'auth_auth0_domain' || true)
    AUTH0_CLIENT_ID=$(bashio::config 'auth_auth0_client_id' || true)

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
    SAML_URL=$(bashio::config 'auth_saml_url' || true)

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
    OIDC_PROVIDER_URL=$(bashio::config 'auth_oidc_provider_url' || true)
    OIDC_CLIENT_ID=$(bashio::config 'auth_oidc_client_id' || true)
    OIDC_CLIENT_SECRET=$(bashio::config 'auth_oidc_client_secret' || true)
    OIDC_LOGOUT_URL=$(bashio::config 'auth_oidc_logout_url' || true)

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

    for scope in $(bashio::config 'auth_oidc_scopes'); do
        OMNI_ARGS+=("--auth-oidc-scopes=${scope}")
    done
fi

# Add initial users
if bashio::config.has_value 'initial_users'; then
    for user in $(bashio::config 'initial_users'); do
        bashio::log.info "Adding initial user: ${user}"
        OMNI_ARGS+=("--initial-users=${user}")
    done
fi

# Set up persistent storage matching upstream volume layout
mkdir -p /share/omni/etcd /share/omni/secondary-storage /share/omni/omnictl
ln -sfn /share/omni/etcd /_out/etcd
ln -sfn /share/omni/secondary-storage /_out/secondary-storage
ln -sfn /share/omni/omnictl /_out/omnictl
ln -sfn /share/omni/omnictl /omnictl

bashio::log.info "Starting Omni with configuration:"
bashio::log.info "  Name: ${NAME}"
bashio::log.info "  Account ID: ${ACCOUNT_ID}"
bashio::log.info "  Domain: ${ADVERTISED_DOMAIN}"
bashio::log.info "  WireGuard IP: ${WIREGUARD_IP}:${WIREGUARD_PORT}"

exec /usr/local/bin/omni "${OMNI_ARGS[@]}"
