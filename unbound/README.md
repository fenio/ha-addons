# Unbound DNS Resolver

A self-managed Home Assistant add-on that provides a recursive DNS resolver using Unbound. All configuration is done through the built-in web UI — no need to edit YAML or restart the addon to change settings.

## Features

- **Web UI Dashboard**: DNS stats, cache hit rate, blocked domains count, uptime
- **Settings Tab**: Configure all server settings (network, performance, cache, security, logging) with live reload
- **Blocklist Management**: Add/remove blocklist URLs, refresh & apply with one click
- **Whitelist**: Exclude domains from blocklists
- **Local DNS Records**: Custom hostname-to-IP mappings with instant apply
- **Query Log**: View recent queries, top domains chart, filter by domain/client
- **Cache Controls**: Flush individual domains or entire cache
- **Recursive DNS Resolution**: Full recursive resolver or forward to upstream servers
- **DNSSEC Validation**: Optional DNSSEC support for secure DNS lookups
- **Dark Mode**: Toggle between light and dark themes

## Installation

1. Add this repository to your Home Assistant add-on store:

   [![Add repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https://github.com/fenio/ha-addons)

   Or manually: **Settings** > **Add-ons** > **Add-on Store** > **⋮** > **Repositories** > Add `https://github.com/fenio/ha-addons`

2. Find "Unbound DNS" in the add-on store and click **Install**
3. Start the addon and open the **Web UI** to configure everything

## Configuration

All settings are managed through the web UI's **Settings** tab. Changes are applied immediately via hot-reload — no addon restart needed (except for thread count changes). There are no options in the HA addon configuration panel.

### Custom Configuration

If the web UI doesn't cover your needs, you can provide your own `unbound.conf`:

1. Enable **Custom Config** in the web UI Settings tab
2. Place your `unbound.conf` file at `/addon_configs/unbound/unbound.conf`
3. Restart the addon

When custom config mode is enabled, all other settings in the Settings tab are ignored — the addon uses your file as-is.

### First Run

On first startup, the addon seeds its config from HA addon defaults. After that, all configuration lives in `/data/config.json` and is managed exclusively through the web UI.

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
