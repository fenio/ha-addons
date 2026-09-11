# Omada Controller (No AVX)

TP-Link Omada Controller add-on for Home Assistant, specifically built for **CPUs without AVX support**.

## Why This Add-on?

The official Omada Controller v6.x requires MongoDB 8.x, which needs AVX CPU instructions. Many older CPUs (and some newer low-power CPUs) don't support AVX, making the standard Omada Controller unusable.

This add-on uses MongoDB 8.0 compiled without AVX instructions by [rnsc/mongodb-without-avx](https://github.com/rnsc/mongodb-without-avx).

## Supported Architectures

- **amd64** only (ARM is not supported)

## Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `enable_hass_ssl` | Use Home Assistant SSL certificates | `false` |
| `certfile` | SSL certificate file (relative to /ssl) | `fullchain.pem` |
| `keyfile` | SSL private key file (relative to /ssl) | `privkey.pem` |
| `enable_workaround_509` | Obsolete compatibility option; no effect on Omada 6.3 | `false` |

## Ports

| Port | Protocol | Description |
|------|----------|-------------|
| 8044 | TCP | Device firmware upgrade HTTPS |
| 8088 | TCP | Management HTTP |
| 8043 | TCP | Management HTTPS |
| 8843 | TCP | Portal HTTPS |
| 19810 | UDP | Device discovery (new) |
| 27001 | UDP | App discovery |
| 29810 | UDP | EAP discovery |
| 29811 | TCP | EAP management v1 |
| 29812 | TCP | EAP adoption |
| 29813-29814 | TCP | EAP management v2 |
| 29815 | TCP | EAP reset |
| 29816-29817 | TCP | EAP manager access |

## First Run

1. Install the add-on
2. Start the add-on
3. Access the web interface at `https://<your-ha-ip>:8043`
4. Complete the Omada Controller setup wizard

## Data Persistence

All data is stored in the add-on's persistent storage and will survive restarts and updates.

## Upgrading

Create a Home Assistant backup before upgrading from `6.2.14.11-ha1`. Backups stop this add-on while its MongoDB data is captured. This release upgrades MongoDB from 7.0 to 8.0 and migrates the Omada application database from 6.2 to 6.3. Direct rollback is not supported; restore the backup to return to the previous release.

## Credits

- [mbentley/docker-omada-controller](https://github.com/mbentley/docker-omada-controller) - Base Docker scripts
- [jkunczik/home-assistant-omada](https://github.com/jkunczik/home-assistant-omada) - Original HA add-on inspiration
- [rnsc/mongodb-without-avx](https://github.com/rnsc/mongodb-without-avx) - MongoDB 8 without AVX instructions
