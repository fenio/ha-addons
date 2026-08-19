"""Unbound DNS resolver web UI for Home Assistant ingress."""

import importlib.util
import ipaddress
import json
import logging
import os
import re
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request

# Load config_gen from explicit path to avoid sys.path issues in container
_config_gen_path = os.environ.get("UNBOUND_CONFIG_GEN_PATH", "/web/config_gen.py")
_spec = importlib.util.spec_from_file_location("config_gen", _config_gen_path)
config_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config_gen)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

BLOCKLISTS_FILE = "/data/blocklists.json"
BLOCKLIST_STATUS_FILE = "/data/blocklist_status.json"
BLOCKLIST_CONF = "/etc/unbound/blocklist.conf"
WHITELIST_FILE = "/data/whitelist.json"
LOCAL_RECORDS_FILE = "/data/local_records.json"
STUB_ZONES_FILE = "/data/stub_zones.json"
LOCAL_RECORDS_CONF = "/etc/unbound/local_records.conf"
QUERY_LOG_FILE = "/data/unbound_queries.log"
CUSTOM_CONFIG_WARNING_FILE = "/data/custom_config_warning.txt"
CUSTOM_CONFIG_PATH = "/config/unbound.conf"
OVERLAY_WARNING_FILE = "/data/overlay_warning.txt"
OVERLAY_FILE = "/config/unbound-overlay.conf"
EXTRA_FILE = "/config/unbound-extra.conf"
SETTINGS_BACKUP_FORMAT = "ha-unbound-settings"
SETTINGS_BACKUP_VERSION = 2
SETTINGS_BACKUP_SUPPORTED_VERSIONS = (1, 2)
SETTINGS_BACKUP_MAX_BYTES = 2 * 1024 * 1024
SETTINGS_BACKUP_FILES = {
    "unbound.conf": CUSTOM_CONFIG_PATH,
    "unbound-overlay.conf": OVERLAY_FILE,
    "unbound-extra.conf": EXTRA_FILE,
}

_BLOCKLIST_SKIP_DOMAINS = frozenset({
    "localhost", "localhost.localdomain", "local", "broadcasthost",
    "ip6-localhost", "ip6-loopback", "ip6-localnet",
    "ip6-mcastprefix", "ip6-allnodes", "ip6-allrouters", "ip6-allhosts",
})

# Matches unbound query/reply log lines. Both share the first five fields:
#   [1708012345] unbound[1:0] info: 192.168.1.1 example.com. A IN
# Reply lines (log-replies: yes) tack on rcode/rtt/size after the class.
# We anchor strictly enough to skip other info: lines (stats, validation
# failures, keytag generation, etc.) that previously produced garbage rows.
_LOG_QUERY_RE = re.compile(
    r"\[(\d+)\]\s+unbound\[\d+:\d+\]\s+info:\s+"
    r"(\S+)\s+"                          # client (IP, validated below)
    r"(\S+\.)\s+"                        # domain (must end with a dot)
    r"([A-Z][A-Z0-9]*)\s+"               # RR type
    r"(IN|CH|HS|ANY|NONE)"               # DNS class
    r"(?:\s|$)"
)

_unbound_version = None
_settings_lock = threading.RLock()
_blocklist_refresh_lock = threading.Lock()


# --- JSON helpers ---

def synchronized_settings(function):
    """Serialize mutations of persistent settings and generated config."""
    def wrapped(*args, **kwargs):
        with _settings_lock:
            return function(*args, **kwargs)

    wrapped.__name__ = function.__name__
    return wrapped


def valid_blocklist_url(value):
    """Return True for absolute HTTP(S) URLs safe to pass to curl."""
    if not isinstance(value, str) or not value.strip() or value.startswith("-"):
        return False
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)

def load_blocklists():
    """Load blocklist URLs from persistent storage."""
    if not os.path.exists(BLOCKLISTS_FILE):
        return []
    with open(BLOCKLISTS_FILE, "r") as f:
        return json.load(f)


def save_blocklists(blocklists):
    """Save blocklist URLs to persistent storage."""
    with open(BLOCKLISTS_FILE, "w") as f:
        json.dump(blocklists, f, indent=2)


def load_blocklist_status():
    """Load per-blocklist status (domain count, last refresh, errors)."""
    if not os.path.exists(BLOCKLIST_STATUS_FILE):
        return {}
    with open(BLOCKLIST_STATUS_FILE, "r") as f:
        return json.load(f)


def save_blocklist_status(status):
    """Save per-blocklist status."""
    with open(BLOCKLIST_STATUS_FILE, "w") as f:
        json.dump(status, f, indent=2)


def load_whitelist():
    """Load whitelisted domains."""
    if not os.path.exists(WHITELIST_FILE):
        return []
    with open(WHITELIST_FILE, "r") as f:
        return json.load(f)


def save_whitelist(whitelist):
    """Save whitelisted domains."""
    with open(WHITELIST_FILE, "w") as f:
        json.dump(whitelist, f, indent=2)


def load_stub_zones():
    """Load stub zones."""
    if not os.path.exists(STUB_ZONES_FILE):
        return []
    with open(STUB_ZONES_FILE, "r") as f:
        return json.load(f)


def save_stub_zones(zones):
    """Save stub zones."""
    with open(STUB_ZONES_FILE, "w") as f:
        json.dump(zones, f, indent=2)


def load_local_records():
    """Load local DNS records."""
    if not os.path.exists(LOCAL_RECORDS_FILE):
        return []
    with open(LOCAL_RECORDS_FILE, "r") as f:
        return json.load(f)


def save_local_records(records):
    """Save local DNS records."""
    with open(LOCAL_RECORDS_FILE, "w") as f:
        json.dump(records, f, indent=2)


def _read_optional_text(path):
    """Read a text file if it exists."""
    if not os.path.exists(path):
        return None
    if os.path.getsize(path) > SETTINGS_BACKUP_MAX_BYTES:
        raise ValueError(f"Custom configuration file is too large to export: {path}")
    with open(path, "r") as f:
        return f.read()


def create_settings_backup():
    """Build a portable backup of all user-managed settings."""
    source_paths = [
        config_gen.CONFIG_FILE,
        BLOCKLISTS_FILE,
        WHITELIST_FILE,
        LOCAL_RECORDS_FILE,
        STUB_ZONES_FILE,
        *SETTINGS_BACKUP_FILES.values(),
    ]
    source_size = sum(
        os.path.getsize(path) for path in source_paths if os.path.exists(path)
    )
    if source_size > SETTINGS_BACKUP_MAX_BYTES:
        raise ValueError("Settings files exceed the 2 MiB backup limit.")

    custom_files = {}
    for name, path in SETTINGS_BACKUP_FILES.items():
        content = _read_optional_text(path)
        if content is not None:
            custom_files[name] = content

    return {
        "format": SETTINGS_BACKUP_FORMAT,
        "version": SETTINGS_BACKUP_VERSION,
        "exported_at": int(time.time()),
        "config": config_gen.load_config(),
        "blocklists": load_blocklists(),
        "whitelist": load_whitelist(),
        "local_records": load_local_records(),
        "stub_zones": load_stub_zones(),
        "custom_files": custom_files,
    }


def validate_settings_backup(data):
    """Validate and normalize an imported settings backup."""
    errors = []
    normalized = {}

    if not isinstance(data, dict):
        return None, ["Backup must contain a JSON object."]
    if data.get("format") != SETTINGS_BACKUP_FORMAT:
        errors.append("Not an Unbound settings backup.")
    if data.get("version") not in SETTINGS_BACKUP_SUPPORTED_VERSIONS:
        errors.append(f"Unsupported backup version: {data.get('version')!r}.")

    config = data.get("config")
    if not isinstance(config, dict):
        errors.append("config must be an object.")
    else:
        unknown = sorted(set(config) - set(config_gen.CONFIG_SCHEMA))
        if unknown:
            errors.append("config contains unknown settings: " + ", ".join(unknown))
        merged = {
            key: schema["default"]
            for key, schema in config_gen.CONFIG_SCHEMA.items()
        }
        merged.update(config)
        errors.extend(config_gen.validate_config(merged))
        normalized["config"] = merged

    blocklists = data.get("blocklists")
    if not isinstance(blocklists, list):
        errors.append("blocklists must be a list.")
    elif any(not valid_blocklist_url(value) for value in blocklists):
        errors.append("blocklists must contain only absolute HTTP or HTTPS URLs.")
    else:
        normalized["blocklists"] = blocklists

    whitelist = data.get("whitelist")
    if not isinstance(whitelist, list):
        errors.append("whitelist must be a list.")
    elif any(
        not isinstance(value, str) or not value.strip() for value in whitelist
    ):
        errors.append("whitelist must contain only non-empty strings.")
    else:
        normalized["whitelist"] = whitelist

    records = data.get("local_records")
    if not isinstance(records, list):
        errors.append("local_records must be a list.")
    elif any(
        not isinstance(record, dict)
        or not isinstance(record.get("hostname"), str)
        or not record["hostname"].strip()
        or not isinstance(record.get("ip"), str)
        or not record["ip"].strip()
        or not isinstance(record.get("allow_acme_challenge", False), bool)
        for record in records
    ):
        errors.append(
            "local_records entries require non-empty hostname and ip strings "
            "and an optional Boolean allow_acme_challenge value."
        )
    else:
        normalized["local_records"] = [
            {
                "hostname": record["hostname"],
                "ip": record["ip"],
                "allow_acme_challenge": record.get("allow_acme_challenge", False),
            }
            for record in records
        ]

    zones = data.get("stub_zones")
    if not isinstance(zones, list):
        errors.append("stub_zones must be a list.")
    elif any(
        not isinstance(zone, dict)
        or not isinstance(zone.get("name"), str)
        or not zone["name"].strip()
        or not isinstance(zone.get("addr"), str)
        or not zone["addr"].strip()
        for zone in zones
    ):
        errors.append("stub_zones entries require non-empty name and addr strings.")
    else:
        normalized["stub_zones"] = [
            {"name": zone["name"], "addr": zone["addr"]}
            for zone in zones
        ]

    custom_files = data.get("custom_files")
    if not isinstance(custom_files, dict):
        errors.append("custom_files must be an object.")
    else:
        unknown = sorted(set(custom_files) - set(SETTINGS_BACKUP_FILES))
        if unknown:
            errors.append("custom_files contains unknown files: " + ", ".join(unknown))
        invalid = [
            name for name, content in custom_files.items()
            if not isinstance(content, str)
        ]
        if invalid:
            errors.append(
                "custom_files entries must contain text: "
                + ", ".join(sorted(invalid))
            )
        normalized["custom_files"] = custom_files

    if (
        isinstance(normalized.get("config"), dict)
        and normalized["config"].get("custom_config")
        and (
            not isinstance(custom_files, dict)
            or not custom_files.get("unbound.conf", "").strip()
        )
    ):
        errors.append("custom_config requires a non-empty unbound.conf file.")

    return (normalized if not errors else None), errors


def _snapshot_files(paths):
    """Read files for transactional rollback."""
    snapshot = {}
    for path in paths:
        if os.path.islink(path):
            raise ValueError(f"Managed settings path cannot be a symlink: {path}")
        if os.path.exists(path):
            with open(path, "rb") as f:
                snapshot[path] = {
                    "content": f.read(),
                    "mode": os.stat(path).st_mode & 0o777,
                }
        else:
            snapshot[path] = None
    return snapshot


def _write_bytes_atomic(path, content, mode=None):
    """Atomically replace a file with bytes."""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    if mode is None:
        if os.path.exists(path) and not os.path.islink(path):
            mode = os.stat(path).st_mode & 0o777
        else:
            mode = 0o600
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _write_json_atomic(path, value):
    content = (json.dumps(value, indent=2) + "\n").encode("utf-8")
    _write_bytes_atomic(path, content)


def _restore_files(snapshot):
    """Restore files captured by _snapshot_files."""
    for path, state in snapshot.items():
        if state is None:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
        else:
            _write_bytes_atomic(path, state["content"], mode=state["mode"])


def write_local_records_conf(records):
    """Write /etc/unbound/local_records.conf from records list."""
    content = config_gen.generate_local_records_conf(records).encode("utf-8")
    _write_bytes_atomic(LOCAL_RECORDS_CONF, content)


def parse_query_log(text):
    """Parse unbound query log text into structured dicts."""
    entries = []
    for line in text.split("\n"):
        m = _LOG_QUERY_RE.search(line)
        if not m:
            continue
        client = m.group(2)
        try:
            ipaddress.ip_address(client)
        except ValueError:
            continue
        entries.append({
            "timestamp": int(m.group(1)),
            "client": client,
            "domain": m.group(3).rstrip("."),
            "type": m.group(4),
            "class": m.group(5),
        })
    return entries


# --- Helpers ---

def get_ingress_path():
    """Get the ingress base path from environment or headers."""
    return os.environ.get("INGRESS_PATH", "")


def run_unbound_control(cmd, retries=0):
    """Run an unbound-control command and return (output, ok).

    On success: returns stdout. On failure: returns combined stderr+stdout so
    OpenSSL/TLS diagnostics aren't lost. Set retries>0 to retry transient
    failures (e.g. control-channel races during reload).
    """
    last_err = ""
    for attempt in range(retries + 1):
        try:
            result = subprocess.run(
                ["unbound-control"] + cmd,
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout, True
            last_err = (result.stderr.strip() + "\n" + result.stdout.strip()).strip()
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            last_err = str(e)
        if attempt < retries:
            time.sleep(0.5)
    return last_err or "Unknown error", False


def parse_stats(raw_stats):
    """Parse unbound-control stats output into a structured dict."""
    stats = {}
    for line in raw_stats.strip().split("\n"):
        if "=" in line:
            key, value = line.split("=", 1)
            stats[key.strip()] = value.strip()
    return stats


def get_unbound_version():
    """Return the installed Unbound version, cached for the process lifetime."""
    global _unbound_version
    if _unbound_version is not None:
        return _unbound_version

    try:
        result = subprocess.run(
            ["unbound", "-V"], capture_output=True, text=True, timeout=5
        )
        match = re.search(r"^Version\s+(\S+)", result.stdout, re.MULTILINE)
        _unbound_version = match.group(1) if match else "N/A"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        _unbound_version = "N/A"
    return _unbound_version


# --- Routes ---

@app.route("/")
def index():
    """Serve the main dashboard."""
    ingress_path = get_ingress_path()
    return render_template("index.html", ingress_path=ingress_path)


@app.route("/api/stats")
def api_stats():
    """Return DNS statistics from unbound-control."""
    raw, ok = run_unbound_control(["stats_noreset"])
    if not ok:
        return jsonify({"error": "Failed to get stats", "detail": raw}), 500

    stats = parse_stats(raw)

    # Unbound in multi-threaded mode emits per-thread keys (threadN.*) plus
    # cumulative total.* keys, and does not emit num.threads — derive it.
    num_threads = sum(
        1 for key in stats
        if key.startswith("thread") and key.endswith(".num.queries")
    )

    total_queries = float(stats.get("total.num.queries", 0))
    cache_hits = float(stats.get("total.num.cachehits", 0))
    cache_miss = float(stats.get("total.num.cachemiss", 0))
    hit_rate = (cache_hits / total_queries * 100) if total_queries > 0 else 0

    # Count blocked domains from blocklist.conf
    blocked_count = 0
    if os.path.exists(BLOCKLIST_CONF):
        with open(BLOCKLIST_CONF, "r") as f:
            blocked_count = sum(1 for line in f if line.startswith("local-zone:"))

    uptime = float(stats.get("time.up", 0))
    queries_per_sec = round(total_queries / uptime, 1) if uptime > 0 else 0

    # Response codes
    rcodes = {}
    for key, val in stats.items():
        if key.startswith("num.answer.rcode."):
            rcode = key.split(".")[-1]
            count = int(float(val))
            if count > 0:
                rcodes[rcode] = count

    # Query types
    qtypes = {}
    for key, val in stats.items():
        if key.startswith("num.query.type."):
            qtype = key.split(".")[-1]
            count = int(float(val))
            if count > 0:
                qtypes[qtype] = count

    # Memory usage (bytes)
    memory = {}
    for key, val in stats.items():
        if key.startswith("mem."):
            label = key.replace("mem.", "")
            memory[label] = int(float(val))

    return jsonify({
        "unbound_version": get_unbound_version(),
        "total_queries": int(total_queries),
        "cache_hits": int(cache_hits),
        "cache_misses": int(cache_miss),
        "cache_hit_rate": round(hit_rate, 1),
        "blocked_domains": blocked_count,
        "num_threads": num_threads if num_threads > 0 else "N/A",
        "uptime": stats.get("time.up", "N/A"),
        "queries_per_sec": queries_per_sec,
        "recursion_time_avg": stats.get("total.recursion.time.avg", "N/A"),
        "recursion_time_median": stats.get("total.recursion.time.median", "N/A"),
        "prefetch": int(float(stats.get("total.num.prefetch", 0))),
        "unwanted_queries": int(float(stats.get("unwanted.queries", 0))),
        "unwanted_replies": int(float(stats.get("unwanted.replies", 0))),
        "rcodes": rcodes,
        "qtypes": qtypes,
        "memory": memory,
        "raw": stats,
    })


# --- Blocklists ---

@app.route("/api/blocklists")
def api_blocklists_list():
    """List all configured blocklists with per-URL status."""
    urls = load_blocklists()
    status = load_blocklist_status()
    result = []
    for url in urls:
        info = status.get(url, {})
        result.append({
            "url": url,
            "domains": info.get("domains", None),
            "last_refresh": info.get("last_refresh", None),
            "error": info.get("error", None),
        })
    return jsonify(result)


@app.route("/api/blocklists", methods=["POST"])
@synchronized_settings
def api_blocklists_add():
    """Add a new blocklist URL."""
    data = request.get_json()
    if not data or "url" not in data:
        return jsonify({"error": "Missing 'url' field"}), 400

    url = data["url"].strip()
    if not valid_blocklist_url(url):
        return jsonify({"error": "URL must use HTTP or HTTPS"}), 400

    blocklists = load_blocklists()
    if url in blocklists:
        return jsonify({"error": "URL already exists"}), 409

    blocklists.append(url)
    save_blocklists(blocklists)
    return jsonify({"status": "added", "url": url}), 201


@app.route("/api/blocklists/<int:idx>", methods=["DELETE"])
@synchronized_settings
def api_blocklists_remove(idx):
    """Remove a blocklist by index."""
    blocklists = load_blocklists()
    if idx < 0 or idx >= len(blocklists):
        return jsonify({"error": "Invalid index"}), 404

    removed = blocklists.pop(idx)
    save_blocklists(blocklists)

    # Clean up status for removed URL
    status = load_blocklist_status()
    status.pop(removed, None)
    save_blocklist_status(status)

    return jsonify({"status": "removed", "url": removed})


def _do_blocklist_refresh():
    """Core blocklist refresh logic. Returns dict with results."""
    if not _blocklist_refresh_lock.acquire(blocking=False):
        return {
            "status": "busy",
            "domains_blocked": 0,
            "errors": [{"url": "", "error": "A refresh is already running."}],
            "reload_ok": False,
        }

    try:
        with _settings_lock:
            blocklists = load_blocklists()
            whitelist_values = load_whitelist()
            whitelist = set(domain.lower() for domain in whitelist_values)
            status = load_blocklist_status()

        all_domains = set()
        errors = []

        for url in blocklists:
            url_domains = set()
            try:
                result = subprocess.run(
                    [
                        "curl", "-sS", "--max-time", "30",
                        "--proto", "=http,https", "--", url,
                    ],
                    capture_output=True, text=True, timeout=35
                )
                if result.returncode != 0:
                    errors.append({"url": url, "error": result.stderr})
                    status[url] = {
                        "domains": 0,
                        "last_refresh": time.time(),
                        "error": result.stderr.strip(),
                    }
                    continue

                for line in result.stdout.split("\n"):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split()
                    if len(parts) >= 2 and parts[0] in ("0.0.0.0", "127.0.0.1"):
                        domain = parts[1].strip().lower()
                        if domain and domain not in _BLOCKLIST_SKIP_DOMAINS:
                            url_domains.add(domain)

                all_domains |= url_domains
                status[url] = {
                    "domains": len(url_domains),
                    "last_refresh": time.time(),
                    "error": None,
                }
            except Exception as e:
                errors.append({"url": url, "error": str(e)})
                status[url] = {
                    "domains": 0,
                    "last_refresh": time.time(),
                    "error": str(e),
                }

        # Subtract whitelisted domains
        all_domains -= whitelist

        with _settings_lock:
            if (
                load_blocklists() != blocklists
                or load_whitelist() != whitelist_values
            ):
                errors.append({
                    "url": "",
                    "error": "Settings changed during refresh; results were not applied.",
                })
                return {
                    "status": "stale",
                    "domains_blocked": 0,
                    "errors": errors,
                    "reload_ok": False,
                }

            save_blocklist_status(status)
            content = "".join(
                f'local-zone: "{domain}." always_refuse\n'
                for domain in sorted(all_domains)
            )
            _write_bytes_atomic(BLOCKLIST_CONF, content.encode("utf-8"))

            # Reload unbound to pick up changes
            _, reload_ok = run_unbound_control(["reload"], retries=1)

        return {
            "status": "refreshed",
            "domains_blocked": len(all_domains),
            "errors": errors,
            "reload_ok": reload_ok,
        }
    finally:
        _blocklist_refresh_lock.release()


@app.route("/api/blocklists/refresh", methods=["POST"])
def api_blocklists_refresh():
    """Re-download all blocklists, subtract whitelist, and reload unbound."""
    return jsonify(_do_blocklist_refresh())


# --- Whitelist ---

@app.route("/api/whitelist")
def api_whitelist_list():
    """List all whitelisted domains."""
    return jsonify(load_whitelist())


@app.route("/api/whitelist", methods=["POST"])
@synchronized_settings
def api_whitelist_add():
    """Add a domain to the whitelist."""
    data = request.get_json()
    if not data or "domain" not in data:
        return jsonify({"error": "Missing 'domain' field"}), 400

    domain = data["domain"].strip().lower()
    if not domain:
        return jsonify({"error": "Domain cannot be empty"}), 400

    whitelist = load_whitelist()
    if domain in whitelist:
        return jsonify({"error": "Domain already whitelisted"}), 409

    whitelist.append(domain)
    save_whitelist(whitelist)
    return jsonify({"status": "added", "domain": domain}), 201


@app.route("/api/whitelist/<int:idx>", methods=["DELETE"])
@synchronized_settings
def api_whitelist_remove(idx):
    """Remove a whitelisted domain by index."""
    whitelist = load_whitelist()
    if idx < 0 or idx >= len(whitelist):
        return jsonify({"error": "Invalid index"}), 404

    removed = whitelist.pop(idx)
    save_whitelist(whitelist)
    return jsonify({"status": "removed", "domain": removed})


# --- Local Records ---

@app.route("/api/local-records")
def api_local_records_list():
    """List all local DNS records."""
    return jsonify(load_local_records())


@app.route("/api/local-records", methods=["POST"])
@synchronized_settings
def api_local_records_add():
    """Add a local DNS record."""
    data = request.get_json()
    if not data or "hostname" not in data or "ip" not in data:
        return jsonify({"error": "Missing 'hostname' and/or 'ip' field"}), 400

    hostname = data["hostname"].strip().lower()
    ip = data["ip"].strip()
    allow_acme_challenge = data.get("allow_acme_challenge", False)
    if not hostname or not ip:
        return jsonify({"error": "Hostname and IP cannot be empty"}), 400
    if not isinstance(allow_acme_challenge, bool):
        return jsonify({"error": "allow_acme_challenge must be a Boolean"}), 400

    records = load_local_records()

    # Check for duplicate hostname
    for rec in records:
        if rec["hostname"] == hostname:
            return jsonify({"error": "Hostname already exists"}), 409

    previous_records = [record.copy() for record in records]
    records.append({
        "hostname": hostname,
        "ip": ip,
        "allow_acme_challenge": allow_acme_challenge,
    })
    save_local_records(records)
    write_local_records_conf(records)

    reload_output, reload_ok = run_unbound_control(["reload"], retries=1)
    if not reload_ok:
        save_local_records(previous_records)
        write_local_records_conf(previous_records)
        rollback_output, rollback_ok = run_unbound_control(["reload"], retries=1)
        detail = reload_output
        if not rollback_ok:
            detail += f" Rollback reload also failed: {rollback_output}"
        return jsonify({
            "error": "Failed to reload Unbound; the new record was removed.",
            "detail": detail,
        }), 500

    return jsonify({
        "status": "added",
        "hostname": hostname,
        "ip": ip,
        "allow_acme_challenge": allow_acme_challenge,
        "reload_ok": True,
    }), 201


@app.route("/api/local-records/<int:idx>", methods=["PATCH"])
@synchronized_settings
def api_local_records_update(idx):
    """Enable or disable public ACME DNS-01 lookups for a local record."""
    data = request.get_json()
    if not data or not isinstance(data.get("allow_acme_challenge"), bool):
        return jsonify({"error": "allow_acme_challenge must be a Boolean"}), 400

    records = load_local_records()
    if idx < 0 or idx >= len(records):
        return jsonify({"error": "Invalid index"}), 404

    enabled = data["allow_acme_challenge"]
    previous = records[idx].copy()
    records[idx]["allow_acme_challenge"] = enabled
    save_local_records(records)
    write_local_records_conf(records)

    reload_output, reload_ok = run_unbound_control(["reload"], retries=1)
    if not reload_ok:
        records[idx] = previous
        save_local_records(records)
        write_local_records_conf(records)
        rollback_output, rollback_ok = run_unbound_control(["reload"], retries=1)
        detail = reload_output
        if not rollback_ok:
            detail += f" Rollback reload also failed: {rollback_output}"
        return jsonify({
            "error": "Failed to reload Unbound; the previous setting was restored.",
            "detail": detail,
        }), 500

    return jsonify({
        "status": "updated",
        "hostname": records[idx]["hostname"],
        "allow_acme_challenge": enabled,
        "reload_ok": True,
    })


@app.route("/api/local-records/<int:idx>", methods=["DELETE"])
@synchronized_settings
def api_local_records_remove(idx):
    """Remove a local DNS record by index."""
    records = load_local_records()
    if idx < 0 or idx >= len(records):
        return jsonify({"error": "Invalid index"}), 404

    previous_records = [record.copy() for record in records]
    removed = records.pop(idx)
    save_local_records(records)
    write_local_records_conf(records)

    reload_output, reload_ok = run_unbound_control(["reload"], retries=1)
    if not reload_ok:
        save_local_records(previous_records)
        write_local_records_conf(previous_records)
        rollback_output, rollback_ok = run_unbound_control(["reload"], retries=1)
        detail = reload_output
        if not rollback_ok:
            detail += f" Rollback reload also failed: {rollback_output}"
        return jsonify({
            "error": "Failed to reload Unbound; the record was restored.",
            "detail": detail,
        }), 500

    return jsonify({
        "status": "removed",
        "hostname": removed["hostname"],
        "reload_ok": True,
    })


# --- Stub Zones ---

@app.route("/api/stub-zones")
def api_stub_zones_list():
    """List all stub zones."""
    return jsonify(load_stub_zones())


@app.route("/api/stub-zones", methods=["POST"])
@synchronized_settings
def api_stub_zones_add():
    """Add a stub zone."""
    data = request.get_json()
    if not data or "name" not in data or "addr" not in data:
        return jsonify({"error": "Missing 'name' and/or 'addr' field"}), 400

    name = data["name"].strip().lower()
    addr = data["addr"].strip()
    if not name or not addr:
        return jsonify({"error": "Name and address cannot be empty"}), 400

    zones = load_stub_zones()

    for z in zones:
        if z["name"] == name:
            return jsonify({"error": "Stub zone already exists"}), 409

    zones.append({"name": name, "addr": addr})
    save_stub_zones(zones)

    # Regenerate config and reload
    config_gen.write_unbound_conf()
    _, reload_ok = run_unbound_control(["reload"], retries=1)
    return jsonify({
        "status": "added",
        "name": name,
        "addr": addr,
        "reload_ok": reload_ok,
    }), 201


@app.route("/api/stub-zones/<int:idx>", methods=["DELETE"])
@synchronized_settings
def api_stub_zones_remove(idx):
    """Remove a stub zone by index."""
    zones = load_stub_zones()
    if idx < 0 or idx >= len(zones):
        return jsonify({"error": "Invalid index"}), 404

    removed = zones.pop(idx)
    save_stub_zones(zones)

    # Regenerate config and reload
    config_gen.write_unbound_conf()
    _, reload_ok = run_unbound_control(["reload"], retries=1)
    return jsonify({
        "status": "removed",
        "name": removed["name"],
        "reload_ok": reload_ok,
    })


# --- Cache ---

@app.route("/api/cache/flush", methods=["POST"])
def api_cache_flush():
    """Flush the entire DNS cache."""
    output, ok = run_unbound_control(["flush_zone", "."])
    if not ok:
        return jsonify({"error": "Failed to flush cache", "detail": output}), 500
    return jsonify({"status": "flushed"})


@app.route("/api/cache/flush-domain", methods=["POST"])
def api_cache_flush_domain():
    """Flush a specific domain from the DNS cache."""
    data = request.get_json()
    if not data or "domain" not in data:
        return jsonify({"error": "Missing 'domain' field"}), 400

    domain = data["domain"].strip()
    if not domain:
        return jsonify({"error": "Domain cannot be empty"}), 400

    output, ok = run_unbound_control(["flush", domain])
    if not ok:
        return jsonify({"error": "Failed to flush domain", "detail": output}), 500
    return jsonify({"status": "flushed", "domain": domain})


# --- Query Log ---

@app.route("/api/query-log")
def api_query_log():
    """Return the last ~100KB of query log parsed into entries."""
    if not os.path.exists(QUERY_LOG_FILE):
        return jsonify([])

    try:
        size = os.path.getsize(QUERY_LOG_FILE)
        read_bytes = min(size, 100 * 1024)
        with open(QUERY_LOG_FILE, "r") as f:
            if size > read_bytes:
                f.seek(size - read_bytes)
                f.readline()  # skip partial line
            text = f.read()
        return jsonify(parse_query_log(text))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/query-log/clear", methods=["POST"])
def api_query_log_clear():
    """Truncate the query log file in place."""
    try:
        if os.path.exists(QUERY_LOG_FILE):
            with open(QUERY_LOG_FILE, "w"):
                pass
        old = QUERY_LOG_FILE + ".old"
        if os.path.exists(old):
            os.unlink(old)
        return jsonify({"ok": True, "message": "Query log cleared."})
    except OSError as e:
        return jsonify({"ok": False, "message": str(e)}), 500


@app.route("/api/top-domains")
def api_top_domains():
    """Return top 25 queried domains from the log."""
    if not os.path.exists(QUERY_LOG_FILE):
        return jsonify([])

    try:
        size = os.path.getsize(QUERY_LOG_FILE)
        read_bytes = min(size, 2 * 1024 * 1024)
        with open(QUERY_LOG_FILE, "r") as f:
            if size > read_bytes:
                f.seek(size - read_bytes)
                f.readline()  # skip partial line
            text = f.read()

        counts = {}
        for entry in parse_query_log(text):
            d = entry["domain"]
            counts[d] = counts.get(d, 0) + 1

        top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:25]
        return jsonify([{"domain": d, "count": c} for d, c in top])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Config (Settings) ---

@app.route("/api/config")
def api_config_get():
    """Return current config and schema for the Settings UI."""
    config = config_gen.load_config()
    result = {"config": config, "schema": config_gen.CONFIG_SCHEMA}
    if os.path.exists(CUSTOM_CONFIG_WARNING_FILE):
        with open(CUSTOM_CONFIG_WARNING_FILE, "r") as f:
            result["custom_config_warning"] = f.read().strip()
    if os.path.exists(OVERLAY_WARNING_FILE):
        with open(OVERLAY_WARNING_FILE, "r") as f:
            result["overlay_warning"] = f.read().strip()
    result["overlay_status"] = {
        "overlay_present": os.path.exists(OVERLAY_FILE)
            and os.path.getsize(OVERLAY_FILE) > 0,
        "extra_present": os.path.exists(EXTRA_FILE)
            and os.path.getsize(EXTRA_FILE) > 0,
    }
    return jsonify(result)


@app.route("/api/config", methods=["PUT"])
@synchronized_settings
def api_config_put():
    """Update config, regenerate unbound.conf, and reload."""
    data = request.get_json()
    if not data:
        return jsonify({"ok": False, "message": "No JSON body"}), 400

    # Merge submitted values onto current config
    current = config_gen.load_config()
    current.update(data)

    result = config_gen.apply_config(current)
    status_code = 200 if result["ok"] else 400
    return jsonify(result), status_code


@app.route("/api/settings/export")
def api_settings_export():
    """Download all user-managed settings as a versioned JSON backup."""
    try:
        with _settings_lock:
            backup = create_settings_backup()
            _, errors = validate_settings_backup(backup)
            if errors:
                return jsonify({
                    "ok": False,
                    "message": "Current settings cannot be exported: "
                    + " ".join(errors),
                }), 409
            body = json.dumps(backup, indent=2) + "\n"
    except (OSError, ValueError, json.JSONDecodeError) as e:
        return jsonify({"ok": False, "message": str(e)}), 413
    if len(body.encode("utf-8")) > SETTINGS_BACKUP_MAX_BYTES:
        return jsonify({
            "ok": False,
            "message": "Settings backup exceeds the 2 MiB import limit.",
        }), 413
    filename = time.strftime("unbound-settings-%Y%m%d-%H%M%S.json", time.gmtime())
    response = app.response_class(body, mimetype="application/json")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@app.route("/api/settings/import", methods=["POST"])
def api_settings_import():
    """Validate, import, and apply a settings backup with file rollback."""
    data = request.get_json(silent=True)
    backup, errors = validate_settings_backup(data)
    if errors:
        return jsonify({"ok": False, "message": " ".join(errors)}), 400

    rollback_paths = [
        config_gen.CONFIG_FILE,
        config_gen.UNBOUND_CONF,
        BLOCKLISTS_FILE,
        BLOCKLIST_STATUS_FILE,
        BLOCKLIST_CONF,
        WHITELIST_FILE,
        LOCAL_RECORDS_FILE,
        LOCAL_RECORDS_CONF,
        STUB_ZONES_FILE,
        OVERLAY_WARNING_FILE,
        *SETTINGS_BACKUP_FILES.values(),
    ]

    if not _settings_lock.acquire(blocking=False):
        return jsonify({
            "ok": False,
            "message": "Settings are currently being modified; try again shortly.",
        }), 409

    try:
        try:
            snapshot = _snapshot_files(rollback_paths)
        except Exception as e:
            return jsonify({
                "ok": False,
                "message": f"Cannot prepare settings import: {e}",
            }), 400

        try:
            _write_json_atomic(BLOCKLISTS_FILE, backup["blocklists"])
            _write_json_atomic(BLOCKLIST_STATUS_FILE, {})
            if not backup["blocklists"]:
                _write_bytes_atomic(BLOCKLIST_CONF, b"")
            _write_json_atomic(WHITELIST_FILE, backup["whitelist"])
            _write_json_atomic(LOCAL_RECORDS_FILE, backup["local_records"])
            _write_json_atomic(STUB_ZONES_FILE, backup["stub_zones"])
            write_local_records_conf(backup["local_records"])

            for name, path in SETTINGS_BACKUP_FILES.items():
                if name in backup["custom_files"]:
                    _write_bytes_atomic(
                        path, backup["custom_files"][name].encode("utf-8")
                    )
                else:
                    try:
                        os.unlink(path)
                    except FileNotFoundError:
                        pass

            if backup["config"].get("custom_config") and os.path.exists(CUSTOM_CONFIG_PATH):
                check = subprocess.run(
                    ["unbound-checkconf", CUSTOM_CONFIG_PATH],
                    capture_output=True, text=True, timeout=10,
                )
                if check.returncode != 0:
                    output = (check.stdout + check.stderr).strip()
                    raise ValueError(f"Custom configuration is invalid: {output}")

            result = config_gen.apply_config(backup["config"])
            if not result["ok"]:
                raise ValueError(result["message"])

            if backup["config"].get("custom_config") and os.path.exists(CUSTOM_CONFIG_PATH):
                custom_content = backup["custom_files"].get("unbound.conf", "")
                _write_bytes_atomic(
                    config_gen.UNBOUND_CONF, custom_content.encode("utf-8")
                )
                custom_ok, custom_output = config_gen.check_conf()
                if not custom_ok:
                    raise ValueError(
                        f"Installed custom configuration is invalid: {custom_output}"
                    )
                reload_ok, reload_output = config_gen._reload_unbound()
                if not reload_ok:
                    raise ValueError(
                        f"Custom configuration reload failed: {reload_output}"
                    )
        except Exception as e:
            try:
                _restore_files(snapshot)
                rollback_ok, rollback_output = config_gen._reload_unbound()
                rollback_message = "Previous settings restored."
                if not rollback_ok:
                    rollback_message = (
                        "Files restored, but rollback reload failed: "
                        + rollback_output
                    )
            except Exception as rollback_error:
                rollback_message = f"Rollback was incomplete: {rollback_error}"
            return jsonify({
                "ok": False,
                "message": f"Import failed: {e} {rollback_message}",
            }), 400

        message = "Settings imported and applied."
        if backup["blocklists"]:
            message += " Refresh blocklists to download and apply their contents."
        if result.get("restart_required"):
            message += " Restart the addon to apply the thread-count change."
        return jsonify({
            "ok": True,
            "message": message,
            "restart_required": result.get("restart_required", False),
            "blocklist_refresh_required": bool(backup["blocklists"]),
        })
    finally:
        _settings_lock.release()


@app.route("/api/config/validate-custom", methods=["POST"])
def api_config_validate_custom():
    """Validate the user's custom unbound.conf without restarting."""
    import shutil
    import tempfile

    if not os.path.exists(CUSTOM_CONFIG_PATH):
        return jsonify({
            "ok": False,
            "message": f"Custom config file not found at {CUSTOM_CONFIG_PATH}",
        })

    try:
        with tempfile.NamedTemporaryFile(suffix=".conf", delete=False) as tmp:
            tmp_path = tmp.name
            shutil.copy2(CUSTOM_CONFIG_PATH, tmp_path)

        result = subprocess.run(
            ["unbound-checkconf", tmp_path],
            capture_output=True, text=True, timeout=10,
        )
        os.unlink(tmp_path)

        if result.returncode == 0:
            return jsonify({"ok": True, "message": "Configuration is valid."})
        else:
            output = (result.stdout + result.stderr).strip()
            return jsonify({"ok": False, "message": output})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)})


# --- Blocklist auto-refresh ---

BLOCKLIST_REFRESH_INTERVAL = 24 * 60 * 60  # 24 hours

_logger = logging.getLogger("unbound-web")


def _blocklist_auto_refresh():
    """Background thread: refresh blocklists every 24 hours."""
    while True:
        time.sleep(BLOCKLIST_REFRESH_INTERVAL)
        try:
            blocklists = load_blocklists()
            if not blocklists:
                continue
            _logger.info("Auto-refreshing blocklists (%d URLs)...", len(blocklists))
            result = _do_blocklist_refresh()
            _logger.info(
                "Auto-refresh complete: %d domains blocked, %d errors",
                result["domains_blocked"], len(result["errors"]),
            )
        except Exception:
            _logger.exception("Auto-refresh failed")


if __name__ == "__main__":
    from waitress import serve

    logging.basicConfig(level=logging.INFO)

    t = threading.Thread(target=_blocklist_auto_refresh, daemon=True)
    t.start()

    port = int(os.environ.get("INGRESS_PORT", 2137))
    serve(
        app,
        host="0.0.0.0",
        port=port,
        max_request_body_size=SETTINGS_BACKUP_MAX_BYTES,
    )
