# Changelog

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
