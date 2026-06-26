# Changelog

## [1.9.0-ha1] - 2026/06/26

- Upgrade Omni 1.8.1 → 1.9.0
- Upstream highlights: cluster template health-check jobs that gate Talos upgrades, embedded machine config on installation media (applied on first boot before reaching Omni), per-class etcd write rate limiting, extension-name validation against the Talos extension catalog, a KubeSpan peer-status view, and maintenance-mode improvements (apply patches and install/upgrade Talos while in maintenance) — see https://github.com/siderolabs/omni/releases/tag/v1.9.0 for the full list
- No addon config schema changes; existing settings continue to work as-is
