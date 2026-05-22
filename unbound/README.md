# Unbound DNS Resolver

A self-managed Home Assistant add-on providing a recursive DNS resolver using [Unbound](https://nlnetlabs.nl/projects/unbound/about/). Fully configured through the built-in web UI — no YAML editing required.

## Features

### Web UI Dashboard
- Hero cards: total queries, cache hit rate, blocked domains
- Server info bar: uptime, threads, avg recursion, prefetches, unwanted queries
- Donut charts for query types (A, AAAA, MX, etc.) and response codes (NOERROR, NXDOMAIN, etc.)
- Memory usage (non-zero entries only)
- Dark mode

### DNS Management
- **Blocklists**: Add/remove blocklist URLs, one-click refresh & apply, automatic daily refresh
- **Whitelist**: Exclude domains from blocklists
- **Local DNS Records**: Custom hostname-to-IP mappings with instant apply
- **Cache Controls**: Flush individual domains or entire cache
- **Query Log**: Recent queries viewer, top domains chart, filter by domain/client

### Server Settings (all hot-reloaded, no restart needed)
- **Network**: Access control, forward servers, DNS-over-TLS, IPv4/IPv6
- **Performance**: Thread count, prefetch, fast server selection, EDNS buffer size, minimal responses
- **Cache**: Message/RRset/negative cache sizing, min/max TTL, negative TTL, serve expired, aggressive NSEC
- **Security & Privacy**: DNSSEC, QNAME minimisation, identity/version hiding, CAPS for ID (0x20)
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

Settings are organized across dedicated tabs (Network, Performance, Cache, Security, Advanced). Changes are applied immediately via hot-reload — no addon restart needed (except for thread count changes).

The only option in the HA addon panel is `log_level` for controlling addon log verbosity.

### Custom Configuration

For advanced users who need full control over `unbound.conf`:

1. Enable **Custom Config** in the web UI Settings tab
2. Place your `unbound.conf` at the addon config path shown in the addon log (e.g. `/addon_configs/<slug>_unbound/unbound.conf`)
3. Restart the addon

When custom config mode is enabled, all other settings are ignored.

### Overlay Files (mix GUI + snippets)

If you want most settings from the GUI but need a few extras unbound supports (e.g. `local-zone "x." nodefault` to free up reserved zones, `auth-zone:`, `view:`), drop one or both of these files into the addon config folder. Overlays are active whenever **Use custom unbound.conf** is **off**.

- `/addon_configs/<slug>_unbound/unbound-overlay.conf` — lines are injected at the **end** of the generated `server:` block. Use this for extra `server:` directives. **Do not** wrap the contents in a `server:` header.

  ```
  local-zone: "yourdomain.lan." nodefault
  local-zone: "168.192.in-addr.arpa." nodefault
  private-address: 10.0.0.0/8
  ```

- `/addon_configs/<slug>_unbound/unbound-extra.conf` — appended **after** the `server:` block. Use this for whole top-level sections.

  ```
  auth-zone:
      name: "lan."
      zonefile: "/config/lan.zone"

  view:
      name: "guest"
      local-zone: "internal.lan." refuse
  ```

Precedence: because unbound keeps the last occurrence of a scalar directive within `server:`, anything in `unbound-overlay.conf` overrides the corresponding GUI value. List-type directives (`local-zone`, `access-control`, …) stack.

If the combined config fails `unbound-checkconf`, the addon falls back to GUI-only and shows a banner in the **Advanced** tab with the validation error so you can fix the snippet without losing DNS.

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
