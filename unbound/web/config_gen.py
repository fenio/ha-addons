"""Unbound config generation and management.

Standalone module — importable from app.py and runnable as CLI:
    python3 /web/config_gen.py --seed-if-needed
    python3 /web/config_gen.py --generate
"""

import json
import os
import shutil
import subprocess
import sys
import time

CONFIG_FILE = "/data/config.json"
OPTIONS_FILE = "/data/options.json"
UNBOUND_CONF = "/etc/unbound/unbound.conf"
BLOCKLIST_CONF = "/etc/unbound/blocklist.conf"
LOCAL_RECORDS_FILE = "/data/local_records.json"
LOCAL_RECORDS_CONF = "/etc/unbound/local_records.conf"
STUB_ZONES_FILE = "/data/stub_zones.json"
QUERY_LOG_FILE = "/data/unbound_queries.log"
LOG_MAX_SIZE = 50 * 1024 * 1024  # 50 MB

# Optional overlay files: user-supplied snippets that augment the generated
# config without forcing them into full custom-config mode. See README.
OVERLAY_FILE = "/config/unbound-overlay.conf"   # injected at end of server: block
EXTRA_FILE = "/config/unbound-extra.conf"       # appended after server: block
OVERLAY_WARNING_FILE = "/data/overlay_warning.txt"

# Schema: key -> {type, default, min?, max?, restart_required?}
CONFIG_SCHEMA = {
    "custom_config": {
        "type": "bool",
        "default": False,
    },
    "access_control": {
        "type": "list",
        "default": ["127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"],
    },
    "num_threads": {
        "type": "int",
        "default": 2,
        "min": 1,
        "max": 16,
        "restart_required": True,
    },
    "prefetch": {
        "type": "bool",
        "default": True,
    },
    "fast_server_permil": {
        "type": "int",
        "default": 500,
        "min": 0,
        "max": 1000,
    },
    "fast_server_num": {
        "type": "int",
        "default": 5,
        "min": 1,
        "max": 20,
    },
    "prefer_ip4": {
        "type": "bool",
        "default": True,
    },
    "do_ip4": {
        "type": "bool",
        "default": True,
    },
    "do_ip6": {
        "type": "bool",
        "default": False,
    },
    "cache_min_ttl": {
        "type": "int",
        "default": 60,
        "min": 0,
        "max": 86400,
    },
    "cache_max_ttl": {
        "type": "int",
        "default": 86400,
        "min": 60,
        "max": 604800,
    },
    "enable_dnssec": {
        "type": "bool",
        "default": True,
    },
    "qname_minimisation": {
        "type": "bool",
        "default": True,
    },
    "hide_identity": {
        "type": "bool",
        "default": True,
    },
    "hide_version": {
        "type": "bool",
        "default": True,
    },
    "forward_servers": {
        "type": "list",
        "default": [],
    },
    "forward_tls": {
        "type": "bool",
        "default": False,
    },
    "verbosity": {
        "type": "int",
        "default": 1,
        "min": 0,
        "max": 5,
    },
    "log_queries": {
        "type": "bool",
        "default": False,
    },
    "log_replies": {
        "type": "bool",
        "default": False,
    },
    # Cache sizing
    "msg_cache_size": {
        "type": "int",
        "default": 4,
        "min": 1,
        "max": 512,
    },
    "rrset_cache_size": {
        "type": "int",
        "default": 8,
        "min": 1,
        "max": 512,
    },
    "neg_cache_size": {
        "type": "int",
        "default": 1,
        "min": 1,
        "max": 128,
    },
    "cache_max_negative_ttl": {
        "type": "int",
        "default": 3600,
        "min": 0,
        "max": 86400,
    },
    # Serve expired
    "serve_expired": {
        "type": "bool",
        "default": False,
    },
    "serve_expired_ttl": {
        "type": "int",
        "default": 86400,
        "min": 0,
        "max": 604800,
    },
    # Aggressive NSEC
    "aggressive_nsec": {
        "type": "bool",
        "default": True,
    },
    # Performance
    "edns_buffer_size": {
        "type": "int",
        "default": 1232,
        "min": 512,
        "max": 4096,
    },
    "minimal_responses": {
        "type": "bool",
        "default": True,
    },
    # Security
    "use_caps_for_id": {
        "type": "bool",
        "default": False,
    },
    # EDNS Client Subnet (ECS) — forward client subnet info to authoritative
    # servers so CDNs can pick a geographically appropriate edge.
    "enable_ecs": {
        "type": "bool",
        "default": False,
    },
}


def _defaults():
    """Return a dict of all schema defaults."""
    return {k: v["default"] for k, v in CONFIG_SCHEMA.items()}


def load_config():
    """Load config from disk, merging schema defaults for missing keys."""
    config = _defaults()
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            stored = json.load(f)
        config.update(stored)
    return config


def save_config(config):
    """Write config to disk."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def generate_local_records_conf(records):
    """Compile local records and optional public ACME challenge exceptions."""
    lines = []
    acme_zones = set()
    for record in records:
        hostname = record["hostname"]
        lines.append(f'local-zone: "{hostname}." redirect')
        lines.append(f'local-data: "{hostname}. A {record["ip"]}"')
        if record.get("allow_acme_challenge") is True:
            acme_zones.add(f"_acme-challenge.{hostname}")

    for zone in sorted(acme_zones):
        lines.append(f'local-zone: "{zone}." transparent')

    return "".join(f"{line}\n" for line in lines)


def write_local_records_conf():
    """Regenerate local_records.conf from persisted local records."""
    with open(LOCAL_RECORDS_FILE, "r") as f:
        records = json.load(f)
    with open(LOCAL_RECORDS_CONF, "w") as f:
        f.write(generate_local_records_conf(records))


def validate_config(config):
    """Validate config values against schema. Returns list of error strings."""
    errors = []
    for key, schema in CONFIG_SCHEMA.items():
        if key not in config:
            continue
        val = config[key]
        stype = schema["type"]

        if stype == "bool":
            if not isinstance(val, bool):
                errors.append(f"{key}: expected bool, got {type(val).__name__}")
        elif stype == "int":
            if not isinstance(val, int) or isinstance(val, bool):
                errors.append(f"{key}: expected int, got {type(val).__name__}")
            else:
                if "min" in schema and val < schema["min"]:
                    errors.append(f"{key}: minimum is {schema['min']}, got {val}")
                if "max" in schema and val > schema["max"]:
                    errors.append(f"{key}: maximum is {schema['max']}, got {val}")
        elif stype == "list":
            if not isinstance(val, list):
                errors.append(f"{key}: expected list, got {type(val).__name__}")

    return errors


def seed_from_options():
    """Seed config.json from options.json if config.json doesn't exist."""
    if os.path.exists(CONFIG_FILE):
        return

    config = _defaults()

    if os.path.exists(OPTIONS_FILE):
        with open(OPTIONS_FILE, "r") as f:
            options = json.load(f)

        # Map options keys to config keys (they use the same names)
        for key in CONFIG_SCHEMA:
            if key in options:
                config[key] = options[key]

    save_config(config)


def _bool_to_yesno(val):
    return "yes" if val else "no"


def _overlay_present(path):
    """True if path exists and contains non-whitespace content."""
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r") as f:
            return bool(f.read().strip())
    except OSError:
        return False


def overlay_files_present():
    """True if either overlay file exists with non-empty content."""
    return _overlay_present(OVERLAY_FILE) or _overlay_present(EXTRA_FILE)


def write_overlay_warning(text):
    """Persist a banner message about overlay fallback."""
    try:
        with open(OVERLAY_WARNING_FILE, "w") as f:
            f.write(text)
    except OSError:
        pass


def clear_overlay_warning():
    """Remove the overlay warning file if present."""
    try:
        os.unlink(OVERLAY_WARNING_FILE)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def generate_unbound_conf(config, include_overlays=True):
    """Generate unbound.conf content from config dict.

    When include_overlays=True (default), emit include: directives for the
    optional /config/unbound-overlay.conf and /config/unbound-extra.conf files
    if they exist. Set False to produce a config that ignores overlays — used
    as a fallback when overlays fail unbound-checkconf.
    """
    # Log rotation
    log_file = ""
    if config.get("log_queries") or config.get("log_replies"):
        log_file = QUERY_LOG_FILE
        if os.path.exists(log_file):
            try:
                size = os.path.getsize(log_file)
                if size > LOG_MAX_SIZE:
                    shutil.move(log_file, log_file + ".old")
                    open(log_file, "w").close()
            except OSError:
                pass

    lines = []
    lines.append("server:")
    lines.append("    # Daemon settings")
    lines.append("    do-daemonize: no")
    lines.append('    username: ""')
    lines.append('    chroot: ""')
    lines.append("")
    lines.append("    # Network settings")
    lines.append("    interface: 0.0.0.0")
    lines.append("    port: 53")
    lines.append(f"    do-ip4: {_bool_to_yesno(config['do_ip4'])}")
    lines.append(f"    do-ip6: {_bool_to_yesno(config['do_ip6'])}")
    lines.append(f"    prefer-ip4: {_bool_to_yesno(config['prefer_ip4'])}")
    lines.append("    do-udp: yes")
    lines.append("    do-tcp: yes")
    lines.append("    do-not-query-localhost: no")
    lines.append("")
    lines.append("    # Performance settings")
    lines.append(f"    num-threads: {config['num_threads']}")
    lines.append(f"    prefetch: {_bool_to_yesno(config['prefetch'])}")
    lines.append(f"    fast-server-permil: {config['fast_server_permil']}")
    lines.append(f"    fast-server-num: {config['fast_server_num']}")
    lines.append(f"    edns-buffer-size: {config.get('edns_buffer_size', 1232)}")
    lines.append(f"    minimal-responses: {_bool_to_yesno(config.get('minimal_responses', True))}")
    lines.append("    msg-cache-slabs: 4")
    lines.append("    rrset-cache-slabs: 4")
    lines.append("    infra-cache-slabs: 4")
    lines.append("    key-cache-slabs: 4")
    lines.append("")
    lines.append("    # Cache settings")
    lines.append(f"    msg-cache-size: {config.get('msg_cache_size', 4)}m")
    lines.append(f"    rrset-cache-size: {config.get('rrset_cache_size', 8)}m")
    lines.append(f"    neg-cache-size: {config.get('neg_cache_size', 1)}m")
    lines.append(f"    cache-min-ttl: {config['cache_min_ttl']}")
    lines.append(f"    cache-max-ttl: {config['cache_max_ttl']}")
    lines.append(f"    cache-max-negative-ttl: {config.get('cache_max_negative_ttl', 3600)}")
    lines.append(f"    serve-expired: {_bool_to_yesno(config.get('serve_expired', False))}")
    lines.append(f"    serve-expired-ttl: {config.get('serve_expired_ttl', 86400)}")
    lines.append(f"    aggressive-nsec: {_bool_to_yesno(config.get('aggressive_nsec', True))}")
    lines.append("")
    lines.append("    # Privacy settings")
    lines.append(f"    qname-minimisation: {_bool_to_yesno(config['qname_minimisation'])}")
    lines.append(f"    hide-identity: {_bool_to_yesno(config['hide_identity'])}")
    lines.append(f"    hide-version: {_bool_to_yesno(config['hide_version'])}")
    lines.append(f"    use-caps-for-id: {_bool_to_yesno(config.get('use_caps_for_id', False))}")
    lines.append("")
    lines.append("    # Root hints for recursive resolution")
    lines.append('    root-hints: "/etc/unbound/root.hints"')
    lines.append("")
    lines.append("    # Trust anchor for DNSSEC")
    lines.append('    auto-trust-anchor-file: "/var/lib/unbound/root.key"')
    lines.append("")
    lines.append("    # Hardening")
    lines.append("    harden-glue: yes")
    lines.append("    harden-dnssec-stripped: yes")
    lines.append("    harden-referral-path: yes")
    if config.get("forward_tls", False):
        # Required for DoT: unbound does not auto-discover system CAs, so without
        # a bundle every handshake fails with "self-signed certificate in chain".
        lines.append('    tls-cert-bundle: "/etc/ssl/cert.pem"')
    lines.append("")
    lines.append("    # Statistics")
    lines.append("    extended-statistics: yes")
    lines.append("")
    lines.append("    # Log settings")
    lines.append(f"    verbosity: {config['verbosity']}")
    lines.append(f'    logfile: "{log_file}"')
    lines.append(f"    log-queries: {_bool_to_yesno(config['log_queries'])}")
    lines.append(f"    log-replies: {_bool_to_yesno(config.get('log_replies', False))}")
    lines.append("    log-servfail: yes")
    lines.append("")
    lines.append("    # Include blocklist and local records")
    lines.append(f'    include: "{BLOCKLIST_CONF}"')
    lines.append(f'    include: "{LOCAL_RECORDS_CONF}"')

    # Access control
    for network in config.get("access_control", []):
        lines.append(f"    access-control: {network} allow")

    # Module config: subnetcache (ECS) must come before validator.
    # Default (DNSSEC on, ECS off) is "validator iterator" — leave implicit.
    ecs_on = config.get("enable_ecs", False)
    dnssec_on = config.get("enable_dnssec", True)
    if ecs_on or not dnssec_on:
        modules = []
        if ecs_on:
            modules.append("subnetcache")
        if dnssec_on:
            modules.append("validator")
        modules.append("iterator")
        lines.append("")
        lines.append(f'    module-config: "{" ".join(modules)}"')

    if dnssec_on:
        lines.append("")
        lines.append("    # DNSSEC validation")
        lines.append("    val-clean-additional: yes")

    if ecs_on:
        lines.append("")
        lines.append("    # EDNS Client Subnet")
        lines.append('    client-subnet-zone: "."')
        lines.append("    max-client-subnet-ipv4: 24")
        lines.append("    max-client-subnet-ipv6: 56")

    # User overlay — last in server: block so user-set scalars override the
    # generated ones (unbound keeps the last occurrence within a section).
    if include_overlays and _overlay_present(OVERLAY_FILE):
        lines.append("")
        lines.append("    # User overlay (unbound-overlay.conf)")
        lines.append(f'    include: "{OVERLAY_FILE}"')

    # Remote control
    lines.append("")
    lines.append("remote-control:")
    lines.append("    control-enable: yes")
    lines.append("    control-interface: 127.0.0.1")
    lines.append('    server-key-file: "/etc/unbound/unbound_server.key"')
    lines.append('    server-cert-file: "/etc/unbound/unbound_server.pem"')
    lines.append('    control-key-file: "/etc/unbound/unbound_control.key"')
    lines.append('    control-cert-file: "/etc/unbound/unbound_control.pem"')

    # Forward zone
    forward_servers = config.get("forward_servers", [])
    if forward_servers:
        lines.append("")
        lines.append("forward-zone:")
        lines.append('    name: "."')
        lines.append(f"    forward-tls-upstream: {_bool_to_yesno(config.get('forward_tls', False))}")
        for server in forward_servers:
            lines.append(f"    forward-addr: {server}")

    # Stub zones
    if os.path.exists(STUB_ZONES_FILE):
        try:
            with open(STUB_ZONES_FILE, "r") as f:
                stub_zones = json.load(f)
            for sz in stub_zones:
                if sz.get("name") and sz.get("addr"):
                    lines.append("")
                    lines.append("stub-zone:")
                    lines.append(f'    name: "{sz["name"]}"')
                    lines.append(f"    stub-addr: {sz['addr']}")
        except (json.JSONDecodeError, OSError):
            pass

    # User extra sections (stub-zone/forward-zone/auth-zone/view/python …)
    if include_overlays and _overlay_present(EXTRA_FILE):
        lines.append("")
        lines.append("# User extra sections (unbound-extra.conf)")
        lines.append(f'include: "{EXTRA_FILE}"')

    lines.append("")
    return "\n".join(lines)


def write_unbound_conf(include_overlays=True):
    """Load config, generate conf, write to disk."""
    config = load_config()
    content = generate_unbound_conf(config, include_overlays=include_overlays)
    with open(UNBOUND_CONF, "w") as f:
        f.write(content)


def check_conf():
    """Run unbound-checkconf. Returns (ok, output)."""
    try:
        result = subprocess.run(
            ["unbound-checkconf", UNBOUND_CONF],
            capture_output=True, text=True, timeout=10,
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return False, str(e)


def write_and_validate(config):
    """Generate unbound.conf with overlays, fall back to no-overlay on failure.

    Returns (ok, message). On success, message is "" (overlay clean) or a
    fallback notice (overlay dropped). On failure, message is the checkconf
    error. Side effect: writes/clears OVERLAY_WARNING_FILE accordingly.
    """
    content = generate_unbound_conf(config, include_overlays=True)
    with open(UNBOUND_CONF, "w") as f:
        f.write(content)

    ok, output = check_conf()
    if ok:
        clear_overlay_warning()
        return True, ""

    if not overlay_files_present():
        return False, output

    # Retry without overlays
    content_no = generate_unbound_conf(config, include_overlays=False)
    with open(UNBOUND_CONF, "w") as f:
        f.write(content_no)

    ok2, output2 = check_conf()
    if not ok2:
        return False, output2

    warning = (
        "Overlay disabled — unbound-checkconf rejected the combined config. "
        "Fix unbound-overlay.conf or unbound-extra.conf and reload.\n\n"
        + output
    )
    write_overlay_warning(warning)
    return True, warning


def _reload_unbound():
    """Tell unbound to reload its config.

    Retries once on failure to cover transient control-channel TLS handshake
    races (issue #13).
    """
    last_output = ""
    for attempt in range(2):
        try:
            result = subprocess.run(
                ["unbound-control", "reload"],
                capture_output=True, text=True, timeout=5,
            )
            last_output = (result.stdout + result.stderr).strip()
            if result.returncode == 0:
                return True, last_output
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            last_output = str(e)
        if attempt == 0:
            time.sleep(0.5)
    return False, last_output


def apply_config(new_config):
    """Full pipeline: validate, save, generate, checkconf, rollback on failure, reload.

    Returns dict with keys: ok, message, restart_required.
    """
    errors = validate_config(new_config)
    if errors:
        return {"ok": False, "message": "Validation failed: " + "; ".join(errors)}

    # Check if num_threads changed (requires restart)
    old_config = load_config()
    restart_required = old_config.get("num_threads") != new_config.get("num_threads")

    # Backup current conf
    backup = None
    if os.path.exists(UNBOUND_CONF):
        with open(UNBOUND_CONF, "r") as f:
            backup = f.read()

    # Save config first so write_and_validate sees the new values
    save_config(new_config)

    # Ensure include files exist (they may not if addon started in custom config mode)
    for inc in (BLOCKLIST_CONF, LOCAL_RECORDS_CONF):
        if not os.path.exists(inc):
            open(inc, "w").close()

    # Generate + validate, with overlay fallback
    ok, output = write_and_validate(new_config)
    if not ok:
        # Rollback unbound.conf and stored config
        if backup is not None:
            with open(UNBOUND_CONF, "w") as f:
                f.write(backup)
        save_config(old_config)
        return {"ok": False, "message": f"Config check failed: {output}"}

    overlay_dropped = bool(output)

    # Reload unbound
    reload_ok, reload_msg = _reload_unbound()
    if not reload_ok:
        if backup is not None:
            with open(UNBOUND_CONF, "w") as f:
                f.write(backup)
        else:
            try:
                os.unlink(UNBOUND_CONF)
            except FileNotFoundError:
                pass
        save_config(old_config)
        rollback_ok, rollback_msg = _reload_unbound()
        msg = f"Config reload failed; previous settings restored: {reload_msg}"
        if not rollback_ok:
            msg += f" Rollback reload also failed: {rollback_msg}"
        return {"ok": False, "message": msg, "restart_required": restart_required}

    msg = "Configuration applied successfully."
    if restart_required:
        msg = "Configuration saved. Addon restart required for thread count change to take effect."
    if overlay_dropped:
        msg += " Overlay was disabled — see banner for details."
    return {"ok": True, "message": msg, "restart_required": restart_required}


if __name__ == "__main__":
    if "--seed-if-needed" in sys.argv:
        seed_from_options()
    elif "--generate-local-records" in sys.argv:
        write_local_records_conf()
    elif "--generate" in sys.argv:
        cfg = load_config()
        ok, msg = write_and_validate(cfg)
        if not ok:
            print(f"unbound-checkconf failed: {msg}", file=sys.stderr)
            sys.exit(1)
        if msg:
            print(msg, file=sys.stderr)
    else:
        print(
            "Usage: config_gen.py "
            "[--seed-if-needed | --generate-local-records | --generate]",
            file=sys.stderr,
        )
        sys.exit(1)
