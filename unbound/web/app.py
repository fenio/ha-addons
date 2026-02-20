"""Unbound DNS resolver web UI for Home Assistant ingress."""

import json
import os
import subprocess

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

BLOCKLISTS_FILE = "/data/blocklists.json"
BLOCKLIST_CONF = "/etc/unbound/blocklist.conf"


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

    return jsonify({
        "total_queries": int(total_queries),
        "cache_hits": int(cache_hits),
        "cache_misses": int(cache_miss),
        "cache_hit_rate": round(hit_rate, 1),
        "blocked_domains": blocked_count,
        "num_threads": stats.get("num.threads", "N/A"),
        "uptime": stats.get("time.up", "N/A"),
        "raw": stats,
    })


@app.route("/api/blocklists")
def api_blocklists_list():
    """List all configured blocklists."""
    return jsonify(load_blocklists())


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
    return jsonify({"status": "removed", "url": removed})


@app.route("/api/blocklists/refresh", methods=["POST"])
def api_blocklists_refresh():
    """Re-download all blocklists and reload unbound."""
    blocklists = load_blocklists()

    all_domains = set()
    errors = []

    for url in blocklists:
        try:
            result = subprocess.run(
                ["curl", "-sS", "--max-time", "30", url],
                capture_output=True, text=True, timeout=35
            )
            if result.returncode != 0:
                errors.append({"url": url, "error": result.stderr})
                continue

            for line in result.stdout.split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2 and parts[0] in ("0.0.0.0", "127.0.0.1"):
                    domain = parts[1].strip().lower()
                    if domain and domain not in ("localhost", "localhost.localdomain",
                                                  "local", "broadcasthost",
                                                  "ip6-localhost", "ip6-loopback",
                                                  "ip6-localnet", "ip6-mcastprefix",
                                                  "ip6-allnodes", "ip6-allrouters",
                                                  "ip6-allhosts"):
                        all_domains.add(domain)
        except Exception as e:
            errors.append({"url": url, "error": str(e)})

    # Write unbound blocklist config
    with open(BLOCKLIST_CONF, "w") as f:
        for domain in sorted(all_domains):
            f.write(f'local-zone: "{domain}." always_refuse\n')

    # Reload unbound to pick up changes
    _, reload_ok = run_unbound_control(["reload"])

    return jsonify({
        "status": "refreshed",
        "domains_blocked": len(all_domains),
        "errors": errors,
        "reload_ok": reload_ok,
    })


if __name__ == "__main__":
    port = int(os.environ.get("INGRESS_PORT", 2137))
    app.run(host="0.0.0.0", port=port)
