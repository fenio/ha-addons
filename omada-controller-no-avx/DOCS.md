# Omada Controller (No AVX)

TP-Link Omada Controller add-on for Home Assistant, specifically built for **CPUs without AVX support**.

## Why This Add-on?

The official Omada Controller v6.x requires MongoDB 8.x, which needs AVX CPU instructions. Many older CPUs (and some newer low-power CPUs) don't support AVX, making the standard Omada Controller unusable.

This add-on uses a custom-built MongoDB 7.0 that doesn't require AVX instructions.

## Supported Architectures

- **amd64** only (ARM is not supported)

## Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `enable_hass_ssl` | Use Home Assistant SSL certificates | `false` |
| `certfile` | SSL certificate file (relative to /ssl) | `fullchain.pem` |
| `keyfile` | SSL private key file (relative to /ssl) | `privkey.pem` |
| `enable_workaround_509` | Enable workaround for 509 errors | `false` |

## Ports

| Port | Protocol | Description |
|------|----------|-------------|
| 8088 | TCP | Management HTTP |
| 8043 | TCP | Management HTTPS |
| 8843 | TCP | Portal HTTPS |
| 27001 | UDP | Device discovery |
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

## Credits

- [mbentley/docker-omada-controller](https://github.com/mbentley/docker-omada-controller) - Base Docker scripts
- [jkunczik/home-assistant-omada](https://github.com/jkunczik/home-assistant-omada) - Original HA add-on inspiration
- [fenio/mongodb-no-avx](https://github.com/fenio/mongodb-no-avx) - MongoDB without AVX requirement
