# Changelog

## [6.3.0.45-ha1] - 2026/09/11

- Upgrade TP-Link Omada Controller from 6.2.14.11 to 6.3.0.45
- Upgrade MongoDB without AVX from 7.0.28 to 8.0.26
- Add the 8044/tcp device firmware upgrade HTTPS port
- Fix initialization of empty persistent data volumes
- Restore Home Assistant SSL certificate import
- Use cold Home Assistant backups to capture consistent MongoDB data

## [6.2.14.11] - 2026/07/29

### Changed
- Upgrade to TP-Link Omada Controller 6.2.14.11

## [6.1.0.19] - 2025/01/22

### Changed
- Upgrade to TP-Link Omada Controller 6.1.0.19
- Add new port 19810/udp for device discovery
- Update Java security module arguments

## [6.0.0.25] - 2025/01/07

### Added
- Initial release with unified versioning
- TP-Link Omada Controller 6.0.0.25
- Custom MongoDB 7.0 build without AVX requirements
- SSL certificate support via Home Assistant /ssl directory
- Workaround for issue #509
