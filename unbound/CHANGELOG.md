# Changelog

## [1.25.2-ha1] - 2026/08/14

- Upgrade the Alpine-packaged Unbound from 1.25.1 to 1.25.2
- Include upstream security and robustness fixes for DNSSEC validation, DNS64, auth zones, cache handling, and malformed input
- Show the underlying Unbound version in the Overview server information bar
- Add versioned JSON export/import for UI settings, DNS lists and records, stub zones, and known custom configuration files, with validation and rollback on failure (issue #20)
- No addon config schema changes; existing settings continue to work as-is

## [1.25.1-ha1] - 2026/06/21

- Rebase on Alpine 3.24 base image and upgrade Unbound 1.24.2 → 1.25.1
- 1.25.1 is a security release: 11 CVEs fixed upstream, including a potential remote code execution in DNSSEC validation (CVE-2026-33278), cache poisoning, multiple crashes, and the "Jiggle Attack" mitigation — see https://nlnetlabs.nl/projects/unbound/security-advisories/ for the full list
- No addon config schema changes; existing settings continue to work as-is

## [1.24.2-ha38] - 2026/05/23

- Fix DNS-over-TLS forwarding: emit `tls-cert-bundle: "/etc/ssl/cert.pem"` when forward TLS is enabled so upstream certs validate against the system CA store — without this, every DoT handshake failed with "self-signed certificate in certificate chain" (issue #19)
- Pin `ca-certificates-bundle` explicitly in the image so the bundle is guaranteed present regardless of openssl's transitive deps

## [1.24.2-ha37] - 2026/05/22

- Add overlay-file mode: when the standard custom-config toggle is off, the addon now picks up `/config/unbound-overlay.conf` (injected at the end of the generated `server:` block) and `/config/unbound-extra.conf` (appended after `server:` for full top-level sections like `auth-zone:` / `view:` / `forward-zone:`) — closes issues #10 and #11
- Overlay files are opt-in by presence; existing users with `custom_config: false` or `true` are unaffected unless they drop one of the new filenames
- If `unbound-checkconf` rejects the combined config, the addon retries without overlays, logs a warning, and surfaces the error in the Advanced tab so DNS stays up while the snippet is fixed
- Boot order updated: blocklist/local-records init now happens before config generation so the validator sees all include targets
- Web UI: added an "Overlay Files" section in the Advanced tab with file-presence status and a fallback banner

## [1.24.2-ha36] - 2026/05/22

- Add EDNS Client Subnet (ECS) toggle in Security & Privacy tab (issue #18)
- When enabled, the `subnetcache` module is loaded ahead of `validator`/`iterator` and ECS is forwarded for all zones (`client-subnet-zone: "."`) with privacy-preserving defaults: IPv4 truncated to /24, IPv6 to /56
- Note: unbound stays on 1.24.2 from Alpine 3.23; upstream 1.25.1 will land once it reaches the stable Alpine branch

## [1.24.2-ha35] - 2026/05/03

- Fix Query Log tab showing garbage rows from non-query `info:` lines (issue #17)
- Tighten log parser: validate client as IPv4/IPv6, require trailing dot on domain, restrict class to IN/CH/HS/ANY/NONE
- Split `log-replies` into its own setting; previously it was forced on whenever `log_queries` was enabled, causing every lookup to appear twice
- Add "Clear Log" button in Query Log tab (POST `/api/query-log/clear`)

## [1.24.2-ha34] - 2026/04/30

- Diagnostics for "SSL handshake failed" on Save & Apply (issue #13)
- Surface stderr from `unbound-control` in error messages so OpenSSL/TLS details are no longer dropped
- Retry `unbound-control reload` once on transient failures to cover control-channel races

## [1.24.2-ha33] - 2026/04/29

- Fix dashboard showing "0" prefetches and "N/A" threads in multi-threaded mode (issue #16)
- Read prefetch counter from `total.num.prefetch` instead of non-existent `num.prefetch`
- Derive thread count by counting `threadX.num.queries` keys since unbound does not emit `num.threads`

## [1.24.2-ha32] - 2026/04/20

- Fix "Permission denied" crash on startup caused by runtime chown/chmod failing in HA containers
- Fix autotrust file (`/var/lib/unbound/root.key`) permission denied (issue #14)
- Fix query log permission denied in custom config mode (issue #7)
- Set world-writable permissions on `/var/lib/unbound` at build time instead of runtime
- Use umask trick for query log creation to avoid needing CAP_CHOWN

### Recovery guide (if stuck on ha29-ha31)

If your addon crashes on startup with `chown: Permission denied` or `chmod: Permission denied`
and you can't update because DNS is down, follow these steps:

```bash
# 1. Patch the broken container to get DNS back
DOCKER_ID=$(docker ps -a --filter "name=unbound" --format "{{.ID}}")
docker cp $DOCKER_ID:/run.sh /tmp/run.sh
sed -i '/chown/d;/chmod/d' /tmp/run.sh
docker cp /tmp/run.sh $DOCKER_ID:/run.sh
docker commit $DOCKER_ID ghcr.io/fenio/unbound-amd64:1.24.2-ha31
ha apps restart 6a5ae1ea_unbound

# 2. Temporarily switch DNS so HA supervisor sees internet connectivity
#    (replace address/gateway with your actual values)
ha network update enp1s0 --ipv4-method static --ipv4-address 10.10.10.200/24 --ipv4-gateway 10.10.10.1 --ipv4-nameserver 8.8.8.8

# 3. Wait for supervisor to detect connectivity, then update
sleep 30
ha supervisor repair
ha apps update 6a5ae1ea_unbound

# 4. Revert DNS back to unbound
ha network update enp1s0 --ipv4-method static --ipv4-address 10.10.10.200/24 --ipv4-gateway 10.10.10.1 --ipv4-nameserver 10.10.10.200
```

Note: Replace `amd64` with `aarch64` if on ARM (e.g., Raspberry Pi). Replace the IP
address, gateway, and addon slug with your actual values.

## [1.24.2-ha28] - 2026/03/19

- Fix dark theme colors to match Home Assistant's native dark palette
- Fix tooltip positioning: open downward to prevent clipping at viewport edges
- Fix restart badge layout crowding the tooltip icon on Threads row

## [1.24.2-ha27] - 2026/03/18

- Add new config options: msg-cache-size, rrset-cache-size, neg-cache-size, cache-max-negative-ttl, serve-expired, serve-expired-ttl, aggressive-nsec, edns-buffer-size, minimal-responses, use-caps-for-id
- Split Settings tab into dedicated Network, Performance, Cache, Security, and Advanced tabs
- Add tooltips with descriptions to all settings
- Redesign Overview dashboard: hero cards, compact server info bar, donut charts for query types and response codes, non-zero-only memory display
- Add toast notifications for settings save/reset feedback
- Trim translations/en.yaml to only HA supervisor UI fields (log_level, ports)

## [1.24.2-ha22] - 2026/02/21

- Fix custom config path: use /config (container mount) instead of /addon_configs (host path). Fixes #4.

## [1.24.2-ha20] - 2026/02/21

- Fix addon_configs path: auto-detect directory with debug logging (try hyphen, underscore, and glob fallback)

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
