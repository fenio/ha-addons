# Unbound DNS Resolver

A self-managed Home Assistant add-on providing a recursive DNS resolver using [Unbound](https://nlnetlabs.nl/projects/unbound/about/). Fully configured through the built-in web UI — no YAML editing required.

## Features

### Web UI Dashboard
- Real-time stats: total queries, queries/sec, cache hit rate, cache hits/misses
- Average recursion time, prefetch count
- Query type breakdown (A, AAAA, MX, etc.)
- Response code distribution (NOERROR, NXDOMAIN, SERVFAIL, etc.)
- Memory usage per cache (rrset, message, etc.)
- Unwanted queries/replies security counters
- Human-readable uptime display
- Dark mode

### DNS Management
- **Blocklists**: Add/remove blocklist URLs, one-click refresh & apply, automatic daily refresh
- **Whitelist**: Exclude domains from blocklists
- **Local DNS Records**: Custom hostname-to-IP mappings with instant apply
- **Cache Controls**: Flush individual domains or entire cache
- **Query Log**: Recent queries viewer, top domains chart, filter by domain/client

### Server Settings (all hot-reloaded, no restart needed)
- **Network**: Access control, forward servers, DNS-over-TLS, IPv4/IPv6
- **Performance**: Thread count, prefetch, fast server selection
- **Cache**: Min/max TTL
- **Security & Privacy**: DNSSEC, QNAME minimisation, identity/version hiding
- **Logging**: Verbosity, query logging

### Under the Hood
- Recursive resolver or forwarding mode (including DNS-over-TLS)
- DNSSEC validation
- Docker health check (DNS query monitoring)
- Root hints auto-update on startup
- Config validation with automatic rollback on failure
- Custom `unbound.conf` support for advanced users

## Installation

1. Add this repository to your Home Assistant add-on store:

   [![Add repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https://github.com/fenio/ha-addons)

   Or manually: **Settings** > **Add-ons** > **Add-on Store** > **⋮** > **Repositories** > Add `https://github.com/fenio/ha-addons`

2. Find "Unbound DNS" in the add-on store and click **Install**
3. Start the addon and open the **Web UI** to configure everything

## Configuration

All settings are managed through the web UI's **Settings** tab. Changes are applied immediately via hot-reload — no addon restart needed (except for thread count changes).

The only option in the HA addon panel is `log_level` for controlling addon log verbosity.

### Custom Configuration

For advanced users who need full control over `unbound.conf`:

1. Enable **Custom Config** in the web UI Settings tab
2. Place your `unbound.conf` at the addon config path shown in the addon log (e.g. `/addon_configs/<slug>_unbound/unbound.conf`)
3. Restart the addon

When custom config mode is enabled, all other settings are ignored.

### First Run

On first startup, the addon creates a default configuration. After that, all settings live in `/data/config.json` and are managed exclusively through the web UI.

## Network Configuration

The add-on listens on port **5053** by default (mapped from container port 53).

To use as your network's DNS server:
1. Configure your router's DHCP to distribute your Home Assistant's IP as the DNS server
2. Ensure clients query port 5053, or change the port mapping to 53 in the add-on configuration

## Troubleshooting

### Test DNS Resolution

```bash
dig @<homeassistant-ip> -p 5053 google.com
```

### Check Add-on Logs

View logs in Home Assistant: **Settings** > **Add-ons** > **Unbound DNS** > **Log**

## License

MIT License
