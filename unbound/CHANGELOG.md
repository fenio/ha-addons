# Changelog

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
