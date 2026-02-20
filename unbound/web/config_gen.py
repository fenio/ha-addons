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

CONFIG_FILE = "/data/config.json"
OPTIONS_FILE = "/data/options.json"
UNBOUND_CONF = "/etc/unbound/unbound.conf"
BLOCKLIST_CONF = "/etc/unbound/blocklist.conf"
LOCAL_RECORDS_CONF = "/etc/unbound/local_records.conf"
QUERY_LOG_FILE = "/data/unbound_queries.log"
LOG_MAX_SIZE = 50 * 1024 * 1024  # 50 MB

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
        "default": True,
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


def generate_unbound_conf(config):
    """Generate unbound.conf content from config dict."""
    # Log rotation
    log_file = ""
    if config.get("log_queries"):
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
    lines.append("    msg-cache-slabs: 4")
    lines.append("    rrset-cache-slabs: 4")
    lines.append("    infra-cache-slabs: 4")
    lines.append("    key-cache-slabs: 4")
    lines.append("")
    lines.append("    # Cache settings")
    lines.append(f"    cache-min-ttl: {config['cache_min_ttl']}")
    lines.append(f"    cache-max-ttl: {config['cache_max_ttl']}")
    lines.append("")
    lines.append("    # Privacy settings")
    lines.append(f"    qname-minimisation: {_bool_to_yesno(config['qname_minimisation'])}")
    lines.append(f"    hide-identity: {_bool_to_yesno(config['hide_identity'])}")
    lines.append(f"    hide-version: {_bool_to_yesno(config['hide_version'])}")
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
    lines.append("")
    lines.append("    # Log settings")
    lines.append(f"    verbosity: {config['verbosity']}")
    lines.append(f'    logfile: "{log_file}"')
    lines.append(f"    log-queries: {_bool_to_yesno(config['log_queries'])}")
    lines.append(f"    log-replies: {_bool_to_yesno(config['log_queries'])}")
    lines.append("    log-servfail: yes")
    lines.append("")
    lines.append("    # Include blocklist and local records")
    lines.append(f'    include: "{BLOCKLIST_CONF}"')
    lines.append(f'    include: "{LOCAL_RECORDS_CONF}"')

    # Access control
    for network in config.get("access_control", []):
        lines.append(f"    access-control: {network} allow")

    # DNSSEC
    if config.get("enable_dnssec"):
        lines.append("")
        lines.append("    # DNSSEC validation")
        lines.append("    val-clean-additional: yes")
    else:
        lines.append("")
        lines.append("    # DNSSEC validation disabled")
        lines.append('    module-config: "iterator"')

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

    lines.append("")
    return "\n".join(lines)


def write_unbound_conf():
    """Load config, generate conf, write to disk."""
    config = load_config()
    content = generate_unbound_conf(config)
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


def _reload_unbound():
    """Tell unbound to reload its config."""
    try:
        result = subprocess.run(
            ["unbound-control", "reload"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return False, str(e)


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

    # Save and generate
    save_config(new_config)
    content = generate_unbound_conf(new_config)
    with open(UNBOUND_CONF, "w") as f:
        f.write(content)

    # Check conf
    ok, output = check_conf()
    if not ok:
        # Rollback
        if backup is not None:
            with open(UNBOUND_CONF, "w") as f:
                f.write(backup)
        save_config(old_config)
        return {"ok": False, "message": f"Config check failed: {output}"}

    # Reload unbound
    reload_ok, reload_msg = _reload_unbound()
    if not reload_ok:
        msg = f"Config saved but reload failed: {reload_msg}"
        if restart_required:
            msg += " (addon restart required for thread count change)"
        return {"ok": True, "message": msg, "restart_required": restart_required}

    msg = "Configuration applied successfully."
    if restart_required:
        msg = "Configuration saved. Addon restart required for thread count change to take effect."
    return {"ok": True, "message": msg, "restart_required": restart_required}


if __name__ == "__main__":
    if "--seed-if-needed" in sys.argv:
        seed_from_options()
    elif "--generate" in sys.argv:
        write_unbound_conf()
    else:
        print("Usage: config_gen.py [--seed-if-needed | --generate]", file=sys.stderr)
        sys.exit(1)
