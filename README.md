# Add-ons for Home Assistant

[![License](https://img.shields.io/github/license/fenio/ha-unbound-addon.svg)](LICENSE)

Home Assistant add-ons repository.

## Add-ons

### [Omada Controller (No AVX)](./omada-controller-no-avx)

![Version](https://img.shields.io/badge/version-6.1.0.19--ha1-blue.svg)

TP-Link Omada Controller for CPUs without AVX support. The standard Omada Controller v6.x uses MongoDB which requires AVX CPU instructions, making it incompatible with older/low-power CPUs (Intel Atom, Celeron, older AMD, etc.). This add-on uses a custom-built MongoDB 7.0 without AVX requirements.

### [Unbound DNS](./unbound)

![Version](https://img.shields.io/badge/version-1.24.2--ha17-blue.svg)

Self-managed recursive DNS resolver with a built-in web UI. No YAML editing — everything is configured through the browser.

- **Dashboard**: Queries/sec, cache hit rate, query type & response code charts, memory usage
- **DNS Management**: Blocklists with daily auto-refresh, whitelist, local DNS records, cache controls
- **Settings**: Network, performance, cache, security, logging — all hot-reloaded
- **Advanced**: DNS-over-TLS forwarding, DNSSEC, health checks, custom unbound.conf support

### [DLNA Proxy](./dlna-proxy)

![Version](https://img.shields.io/badge/version-0.6.0--ha1-blue.svg)

Makes a remote DLNA server (e.g., MiniDLNA) discoverable on your local network by broadcasting SSDP alive messages on its behalf. Includes an optional HTTP-aware TCP proxy that rewrites URLs on the fly, enabling access to servers behind VPNs or on different network segments.

### [Omni](./omni)

![Version](https://img.shields.io/badge/version-1.5.4--ha1-blue.svg)

Siderolabs Omni - Kubernetes cluster management platform for Talos Linux. Provides a unified interface for managing Talos-based Kubernetes clusters with secure WireGuard connectivity.

## Installation

1. Click the button below to add this repository:

   [![Add repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https://github.com/fenio/ha-addons)

2. Or manually add the repository URL in Home Assistant:
   - Go to **Settings** > **Add-ons** > **Add-on Store**
   - Click **⋮** (three dots) > **Repositories**
   - Add: `https://github.com/fenio/ha-addons`
   - Click **Add** and **Close**

3. Refresh the add-on store and find add-on to install

## License

MIT License
