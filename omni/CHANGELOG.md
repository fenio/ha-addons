# Changelog
## [1.10.2-ha1] - 2026/08/14

- Upgrade Omni 1.9.1 to 1.10.2, including the 1.9.2 and 1.9.3 fixes
- Upstream highlights: Talos 1.14 configuration support, LifecycleService-based installs and upgrades, live audit-log following and the Auditor role, disabled config patches, multiple image factories, richer support bundles, and extensive UI improvements
- Include the 1.10.1 and 1.10.2 fixes for authentication/logout, machine tunnel stability, config patch editing, reset workflows, image-factory backfill, and machine routing
- Adapt the renamed upstream `--machine-api-advertised-url` startup argument
- Compatibility note: existing patches that set the Kubernetes CA or service-account signing key continue to work unchanged, but Omni 1.10 rejects edits to those fields because Omni owns them
- No addon config schema changes; existing settings and persistent data continue to be used as-is

## [1.9.1-ha1] - 2026/07/11

- Upgrade Omni 1.9.0 → 1.9.1

## [1.9.0-ha1] - 2026/06/26

- Upgrade Omni 1.8.1 → 1.9.0
- Upstream highlights: cluster template health-check jobs that gate Talos upgrades, embedded machine config on installation media (applied on first boot before reaching Omni), per-class etcd write rate limiting, extension-name validation against the Talos extension catalog, a KubeSpan peer-status view, and maintenance-mode improvements (apply patches and install/upgrade Talos while in maintenance) — see https://github.com/siderolabs/omni/releases/tag/v1.9.0 for the full list
- No addon config schema changes; existing settings continue to work as-is
