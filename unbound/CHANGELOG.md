# Changelog

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
