# Unbound DNS Resolver 

A Home Assistant add-on that provides a recursive DNS resolver using Unbound.

## Features

- **Recursive DNS Resolution**: Operates as a full recursive resolver or forwards to upstream servers
- **Local DNS Records**: Define custom hostname to IP mappings
- **DNSSEC Validation**: Optional DNSSEC support for secure DNS lookups
- **Caching**: Configurable DNS cache with TTL settings
- **Privacy**: Query name minimisation and identity hiding
- **Fast Server Selection**: Automatically prefer faster upstream servers
- **Multi-architecture**: Supports amd64, aarch64, armhf, armv7, and i386

## Installation

1. Add this repository to your Home Assistant add-on store:
   
   [![Add repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https://github.com/fenio/ha-addons)

   Or manually: **Settings** > **Add-ons** > **Add-on Store** > **⋮** > **Repositories** > Add `https://github.com/fenio/ha-addons`

2. Find "Unbound DNS" in the add-on store and click **Install**

## Configuration

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `custom_config` | `false` | Use your own `unbound.conf` instead of generated config |
| `access_control` | Private networks | List of networks allowed to query (CIDR notation) |
| `num_threads` | `2` | Number of threads for processing |
| `prefetch` | `true` | Prefetch popular entries before expiry |
| `fast_server_permil` | `500` | Permil of servers to track for fast selection |
| `fast_server_num` | `5` | Number of fast servers to prefer |
| `prefer_ip4` | `true` | Prefer IPv4 for upstream queries |
| `do_ip4` | `true` | Enable IPv4 |
| `do_ip6` | `true` | Enable IPv6 |
| `cache_min_ttl` | `60` | Minimum TTL for cached entries (seconds) |
| `cache_max_ttl` | `86400` | Maximum TTL for cached entries (seconds) |
| `enable_dnssec` | `true` | Enable DNSSEC validation |
| `qname_minimisation` | `true` | Enable query name minimisation |
| `hide_identity` | `true` | Hide server identity |
| `hide_version` | `true` | Hide server version |
| `local_records` | `[]` | List of local DNS records |
| `forward_servers` | `[]` | Upstream DNS servers (empty = recursive mode) |
| `verbosity` | `1` | Log verbosity level (0-5) |
| `log_queries` | `false` | Log all DNS queries |

### Example Configuration

```yaml
access_control:
  - "127.0.0.0/8"
  - "10.10.0.0/16"
prefer_ip4: true
cache_min_ttl: 60
fast_server_permil: 500
fast_server_num: 5
local_records:
  - hostname: "myserver.local"
    ip: "10.10.20.100"
  - hostname: "nas.local"
    ip: "10.10.20.101"
  - hostname: "printer.local"
    ip: "10.10.20.102"
forward_servers: []
```

### Custom Configuration

If the options above don't cover your needs, you can provide your own `unbound.conf` file for full control over Unbound's configuration.

1. Set `custom_config` to `true` in the addon options
2. Place your `unbound.conf` file at `/addon_configs/unbound/unbound.conf`
3. Restart the addon

When custom config mode is enabled, all other addon options (access control, cache settings, forward servers, etc.) are ignored — the addon uses your file as-is.

Your config file must be a valid Unbound configuration. The addon will run `unbound-checkconf` before starting and log an error if the config is invalid.

### Forwarding vs Recursive Mode

- **Recursive mode** (default): Leave `forward_servers` empty. Unbound will query root DNS servers directly.
- **Forwarding mode**: Add upstream servers like `["1.1.1.1", "8.8.8.8"]` to forward queries.

## Network Configuration

The add-on listens on port **5053** by default (mapped from container port 53).

To use as your network's DNS server:
1. Configure your router's DHCP to distribute your Home Assistant's IP as the DNS server
2. Ensure clients query port 5053, or change the port mapping to 53 in the add-on configuration

### Changing the Port

You can modify the port mapping in the add-on's network configuration panel.

## Troubleshooting

### Test DNS Resolution

```bash
dig @<homeassistant-ip> -p 5053 google.com
```

### Check Add-on Logs

View logs in Home Assistant: **Settings** > **Add-ons** > **Unbound DNS** > **Log**

## License

MIT License
