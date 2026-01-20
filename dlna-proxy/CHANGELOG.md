# Changelog

## [0.6.0-ha1] - 2026/01/20

### Changed
- Update dlna-proxy to 0.6.0
  - Async architecture: TCP proxy now uses Tokio tasks instead of OS threads
  - Resource limits: 10MB body size limit and 100 concurrent connection limit
  - Improved error handling: graceful error propagation instead of panics
  - Better container support: SIGTERM handler for Docker/Kubernetes orchestration

## [0.5.0-ha2] - 2026/01/10

### Fixed
- Fix Docker image tag to actually use 0.5.0 (was incorrectly still using 0.4.2)

## [0.5.0-ha1] - 2026/01/09

### Changed
- Update dlna-proxy to 0.5.0

## [0.4.8-ha1] - 2026/01/09

### Changed
- Update dlna-proxy to 0.4.8

## [0.4.2-ha2] - 2026/01/08

### Added
- Expose new dlna-proxy 0.4.2 options (wait/timeouts) in add-on config

## [0.4.2-ha1] - 2026/01/08

### Added
- Initial release
- Broadcasts SSDP alive messages on behalf of a remote DLNA server
- TCP proxy mode for clients that cannot directly reach the remote server
- Configurable broadcast interval
- Network interface selection
- Multi-architecture support (amd64, aarch64)
