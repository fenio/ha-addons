# Home Assistant Add-on: Omni

Siderolabs Omni - Kubernetes cluster management platform for Talos Linux.

## About

[Omni](https://github.com/siderolabs/omni) is a Kubernetes management platform by Siderolabs that provides a unified interface for managing Talos Linux-based Kubernetes clusters. It simplifies cluster creation, machine management, and provides secure connectivity through WireGuard tunnels.

**Note:** Omni is available under a [Business Source License](https://github.com/siderolabs/omni/blob/main/LICENSE) which allows free installations in non-production environments. For production use, please contact [Sidero sales](https://www.siderolabs.com/pricing/).

## Prerequisites

Before starting the add-on, you need to prepare:

### 1. Valid SSL Certificates

Omni requires valid SSL certificates (self-signed certificates will NOT work). You can use:
- Let's Encrypt with certbot
- Your organization's certificate authority
- Any trusted certificate provider

Place your certificates in the Home Assistant `/ssl` directory.

### 2. GPG Key for etcd Encryption

Generate a GPG key for encrypting etcd data:

```bash
# Generate GPG key
gpg --quick-generate-key "Omni (Used for etcd data encryption) omni@example.com" rsa4096 cert never

# Find the fingerprint
gpg --list-secret-keys

# Add encryption subkey and export (replace <fingerprint> with actual value)
gpg --quick-add-key <fingerprint> rsa4096 encr never
gpg --export-secret-key --armor omni@example.com > omni.asc
```

**Important:** Do not add passphrases to the keys.

You can either:
- **Paste the key directly** in the `private_key` configuration field (recommended)
- **Or** place the `omni.asc` file in your Home Assistant `/config` directory and set `private_key_file: "omni.asc"`

### 3. Authentication Provider

Configure one of the supported authentication methods:

- **Auth0**: Create a single-page web application
- **SAML**: Azure AD, Okta, Keycloak, etc.
- **OIDC**: Any OpenID Connect provider

### 4. Network Requirements

Ensure the following ports are accessible:
- `8443` (443 internal): HTTPS Web UI and API
- `8090`: SideroLink API
- `8091`: Event sink
- `8100`: Kubernetes proxy
- `50180/udp`: WireGuard tunnel

## Configuration

### Required Settings

| Option | Description |
|--------|-------------|
| `advertised_domain` | Domain name where Omni is accessible (e.g., `omni.example.com`) |
| `wireguard_advertised_ip` | Public IP address for WireGuard (must be IP, not hostname) |
| `tls_cert` | TLS certificate filename in `/ssl` |
| `tls_key` | TLS private key filename in `/ssl` |
| `private_key` | GPG key content (paste directly) - OR use `private_key_file` |

### Authentication (choose one)

#### Auth0
```yaml
auth_auth0_enabled: true
auth_auth0_domain: "your-tenant.auth0.com"
auth_auth0_client_id: "your-client-id"
initial_users:
  - "admin@example.com"
```

#### SAML
```yaml
auth_saml_enabled: true
auth_saml_url: "https://login.microsoftonline.com/.../federationmetadata/..."
```

#### OIDC
```yaml
auth_oidc_enabled: true
auth_oidc_provider_url: "https://your-oidc-provider.com"
auth_oidc_client_id: "your-client-id"
auth_oidc_client_secret: "your-client-secret"
```

## Example Configuration

```yaml
name: "my-omni"
advertised_domain: "omni.example.com"
wireguard_advertised_ip: "203.0.113.50"
tls_cert: "fullchain.pem"
tls_key: "privkey.pem"
private_key: |
  -----BEGIN PGP PRIVATE KEY BLOCK-----
  ... your key content ...
  -----END PGP PRIVATE KEY BLOCK-----
auth_saml_enabled: true
auth_saml_url: "https://login.microsoftonline.com/your-tenant/federationmetadata/2007-06/federationmetadata.xml"
```

## Data Persistence

Omni stores its etcd database in `/share/omni/etcd`. This data is persisted across add-on restarts and updates.

## Support

- [Omni Documentation](https://docs.siderolabs.com/omni/)
- [Omni GitHub Repository](https://github.com/siderolabs/omni)
- [Siderolabs Support](https://www.siderolabs.com/support/)
