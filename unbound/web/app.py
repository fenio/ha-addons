"""Unbound DNS resolver web UI for Home Assistant ingress."""

import importlib.util
import json
import logging
import os
import re
import subprocess
import threading
import time

from flask import Flask, jsonify, render_template, request

# Load config_gen from explicit path to avoid sys.path issues in container
_spec = importlib.util.spec_from_file_location("config_gen", "/web/config_gen.py")
config_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config_gen)

app = Flask(__name__)

BLOCKLISTS_FILE = "/data/blocklists.json"
BLOCKLIST_STATUS_FILE = "/data/blocklist_status.json"
BLOCKLIST_CONF = "/etc/unbound/blocklist.conf"
WHITELIST_FILE = "/data/whitelist.json"
LOCAL_RECORDS_FILE = "/data/local_records.json"
LOCAL_RECORDS_CONF = "/etc/unbound/local_records.conf"
QUERY_LOG_FILE = "/data/unbound_queries.log"

_BLOCKLIST_SKIP_DOMAINS = frozenset({
    "localhost", "localhost.localdomain", "local", "broadcasthost",
    "ip6-localhost", "ip6-loopback", "ip6-localnet",
    "ip6-mcastprefix", "ip6-allnodes", "ip6-allrouters", "ip6-allhosts",
})

# Matches unbound log query lines like:
# [1708012345] unbound[1:0] info: 192.168.1.1 example.com. A IN
_LOG_QUERY_RE = re.compile(
    r"\[(\d+)\]\s+unbound\[\d+:\d+\]\s+info:\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)"
)


# --- JSON helpers ---

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


def write_local_records_conf(records):
    """Write /etc/unbound/local_records.conf from records list."""
    with open(LOCAL_RECORDS_CONF, "w") as f:
        for rec in records:
            hostname = rec["hostname"]
            ip = rec["ip"]
            f.write(f'local-zone: "{hostname}." redirect\n')
            f.write(f'local-data: "{hostname}. A {ip}"\n')


def parse_query_log(text):
    """Parse unbound query log text into structured dicts."""
    entries = []
    for line in text.split("\n"):
        m = _LOG_QUERY_RE.search(line)
        if m:
            entries.append({
                "timestamp": int(m.group(1)),
                "client": m.group(2),
                "domain": m.group(3).rstrip("."),
                "type": m.group(4),
                "class": m.group(5),
            })
    return entries


# --- Helpers ---

def get_ingress_path():
    """Get the ingress base path from environment or headers."""
    return os.environ.get("INGRESS_PATH", "")


def run_unbound_control(cmd):
    """Run an unbound-control command and return output."""
    try:
        result = subprocess.run(
            ["unbound-control"] + cmd,
            capture_output=True, text=True, timeout=5
        )
        return result.stdout, result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return str(e), False


def parse_stats(raw_stats):
    """Parse unbound-control stats output into a structured dict."""
    stats = {}
    for line in raw_stats.strip().split("\n"):
        if "=" in line:
            key, value = line.split("=", 1)
            stats[key.strip()] = value.strip()
    return stats


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
        "total_queries": int(total_queries),
        "cache_hits": int(cache_hits),
        "cache_misses": int(cache_miss),
        "cache_hit_rate": round(hit_rate, 1),
        "blocked_domains": blocked_count,
        "num_threads": stats.get("num.threads", "N/A"),
        "uptime": stats.get("time.up", "N/A"),
        "queries_per_sec": queries_per_sec,
        "recursion_time_avg": stats.get("total.recursion.time.avg", "N/A"),
        "recursion_time_median": stats.get("total.recursion.time.median", "N/A"),
        "prefetch": int(float(stats.get("num.prefetch", 0))),
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
def api_blocklists_add():
    """Add a new blocklist URL."""
    data = request.get_json()
    if not data or "url" not in data:
        return jsonify({"error": "Missing 'url' field"}), 400

    url = data["url"].strip()
    if not url:
        return jsonify({"error": "URL cannot be empty"}), 400

    blocklists = load_blocklists()
    if url in blocklists:
        return jsonify({"error": "URL already exists"}), 409

    blocklists.append(url)
    save_blocklists(blocklists)
    return jsonify({"status": "added", "url": url}), 201


@app.route("/api/blocklists/<int:idx>", methods=["DELETE"])
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
    blocklists = load_blocklists()
    whitelist = set(d.lower() for d in load_whitelist())
    status = load_blocklist_status()

    all_domains = set()
    errors = []

    for url in blocklists:
        url_domains = set()
        try:
            result = subprocess.run(
                ["curl", "-sS", "--max-time", "30", url],
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

    save_blocklist_status(status)

    # Subtract whitelisted domains
    all_domains -= whitelist

    # Write unbound blocklist config
    with open(BLOCKLIST_CONF, "w") as f:
        for domain in sorted(all_domains):
            f.write(f'local-zone: "{domain}." always_refuse\n')

    # Reload unbound to pick up changes
    _, reload_ok = run_unbound_control(["reload"])

    return {
        "status": "refreshed",
        "domains_blocked": len(all_domains),
        "errors": errors,
        "reload_ok": reload_ok,
    }


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
def api_local_records_add():
    """Add a local DNS record."""
    data = request.get_json()
    if not data or "hostname" not in data or "ip" not in data:
        return jsonify({"error": "Missing 'hostname' and/or 'ip' field"}), 400

    hostname = data["hostname"].strip().lower()
    ip = data["ip"].strip()
    if not hostname or not ip:
        return jsonify({"error": "Hostname and IP cannot be empty"}), 400

    records = load_local_records()

    # Check for duplicate hostname
    for rec in records:
        if rec["hostname"] == hostname:
            return jsonify({"error": "Hostname already exists"}), 409

    records.append({"hostname": hostname, "ip": ip})
    save_local_records(records)
    write_local_records_conf(records)

    _, reload_ok = run_unbound_control(["reload"])
    return jsonify({
        "status": "added",
        "hostname": hostname,
        "ip": ip,
        "reload_ok": reload_ok,
    }), 201


@app.route("/api/local-records/<int:idx>", methods=["DELETE"])
def api_local_records_remove(idx):
    """Remove a local DNS record by index."""
    records = load_local_records()
    if idx < 0 or idx >= len(records):
        return jsonify({"error": "Invalid index"}), 404

    removed = records.pop(idx)
    save_local_records(records)
    write_local_records_conf(records)

    _, reload_ok = run_unbound_control(["reload"])
    return jsonify({
        "status": "removed",
        "hostname": removed["hostname"],
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
    return jsonify({"config": config, "schema": config_gen.CONFIG_SCHEMA})


@app.route("/api/config", methods=["PUT"])
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
    serve(app, host="0.0.0.0", port=port)
