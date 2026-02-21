# Changelog

## [1.24.2-ha19] - 2026/02/21

- Fix addon_configs path: HOSTNAME uses hyphen but directory uses underscore (376df8b2-unbound vs 376df8b2_unbound)

## [1.24.2-ha18] - 2026/02/21

- Fix addon slug detection: use HOSTNAME env var instead of bashio::addon.slug

## [1.24.2-ha17] - 2026/02/21

- Fix custom config path: detect addon slug dynamically instead of hardcoding

## [1.24.2-ha16] - 2026/02/21

- Extended Overview dashboard with queries/sec, cache misses, avg recursion time, prefetch count
- Add query type breakdown chart (A, AAAA, MX, etc.)
- Add response code breakdown chart (NOERROR, NXDOMAIN, SERVFAIL, etc.)
- Add memory usage stats (rrset cache, message cache, etc.)
- Add security section with unwanted queries/replies counters
- Human-readable uptime format (days/hours/minutes)

## [1.24.2-ha15] - 2026/02/21

- Clean up dead seeding code from run.sh (removed bashio option references)
- Add Docker HEALTHCHECK for DNS query monitoring
- Auto-refresh blocklists every 24 hours in background
- Add DNS-over-TLS forwarding toggle in Settings
- Auto-update root hints on startup

## [1.24.2-ha14] - 2026/02/21

- Switch from Flask dev server to Waitress production WSGI server

## [1.24.2-ha13] - 2026/02/21

- Add `log_level` option to HA addon panel for debugging

## [1.24.2-ha12] - 2026/02/21

- Remove all config options from HA addon panel — addon is fully self-managed
- Move `custom_config` toggle into web UI Settings tab
- Update description and documentation to reflect self-managed architecture

## [1.24.2-ha10] - 2026/02/20

- Add Settings tab to web UI for managing all server configuration
- Move config generation from bash heredoc to Python (`config_gen.py`)
- Settings are persisted in `/data/config.json` and hot-reloaded via `unbound-control`
- First run seeds config from HA addon options automatically
- Invalid config changes are rolled back automatically
- Log addon version at startup

## [1.24.2-ha5] - 2026/02/20

- Replace shell while-loop blocklist parser with single-pass awk

## [1.24.2-ha4] - 2026/02/20

- Fix log rotation `local` keyword outside function

## [1.24.2-ha3] - 2026/02/20

- Add ingress web UI with DNS stats, blocklist/whitelist management, local records, query log, cache controls, and dark mode

## [1.24.2-ha2] - 2026/02/20

- Add custom config file support (`custom_config` option)
- Switch from `config:rw` to `addon_config:rw` for proper isolation

## [1.24.2-ha1] - 2026/01/07

- Fix addon config path

## [1.24.1-ha4] - 2026/01/06

- Unify versioning to {upstream}-ha{revision} format
- Add url field to addon config

## [1.24.1-ha3] - 2025/12/29

- Descriptive names and explanations for options
- Update repository address

## [1.24.1-ha2] - 2025/12/29

- AppArmor profile tuning
- Fix AppArmor permissions for s6-overlay and run.sh

## [1.24.1-ha1] - 2025/12/29

- Initial release
- Unbound recursive DNS resolver
- DNSSEC validation support
- Configurable upstream forwarding servers
- Local DNS records (local-zone/local-data)
- Access control configuration
- Cache TTL configuration
- Fast server selection settings
- AppArmor profile for better security rating
- Use port mapping instead of host network
- Multi-architecture support (amd64, aarch64, armhf, armv7, i386)
