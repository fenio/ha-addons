"""Parse common DNS blocklist formats into safe Unbound local zones."""

import ipaddress
import re
import sys


SKIP_DOMAINS = frozenset({
    "localhost", "localhost.localdomain", "local", "broadcasthost",
    "ip6-localhost", "ip6-loopback", "ip6-localnet",
    "ip6-mcastprefix", "ip6-allnodes", "ip6-allrouters", "ip6-allhosts",
})
MAX_DOMAINS = 500_000

_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_ADBLOCK_RE = re.compile(r"^\|\|([^/^$|]+)\^(?:\$(.*))?$")


def normalize_domain(value):
    """Return a normalized DNS name, or None when value is not a safe domain."""
    domain = value.strip().lower().rstrip(".")
    if domain.startswith("*."):
        domain = domain[2:]

    if not domain or len(domain) > 253 or "." not in domain:
        return None
    if domain in SKIP_DOMAINS:
        return None

    try:
        ipaddress.ip_address(domain)
        return None
    except ValueError:
        pass

    labels = domain.split(".")
    if any(not _LABEL_RE.fullmatch(label) for label in labels):
        return None

    return domain


def parse_domains(lines):
    """Parse plain-domain, hosts, wildcard-domain, and Adblock domain entries."""
    domains = set()
    exceptions = set()
    disabled = set()

    for raw_line in lines:
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith(("!", "[")):
            continue

        is_exception = line.startswith("@@")
        adblock_match = _ADBLOCK_RE.fullmatch(line[2:] if is_exception else line)
        if adblock_match:
            modifiers = set((adblock_match.group(2) or "").lower().split(","))
            is_disabled = "badfilter" in modifiers
            candidates = (adblock_match.group(1),)
        else:
            if is_exception:
                continue
            is_disabled = False
            parts = line.split()
            if len(parts) >= 2 and parts[0] in ("0.0.0.0", "127.0.0.1"):
                candidates = parts[1:]
            elif len(parts) == 1:
                candidates = parts
            else:
                continue

        for candidate in candidates:
            domain = normalize_domain(candidate)
            if domain:
                if is_disabled:
                    disabled.add(domain)
                elif is_exception:
                    exceptions.add(domain)
                else:
                    domains.add(domain)

                if len(domains) + len(exceptions) + len(disabled) > MAX_DOMAINS:
                    raise ValueError(f"blocklist exceeds the {MAX_DOMAINS} domain limit")

    return domains - exceptions - disabled


def render_unbound_config(domains):
    """Render normalized domains as deterministic Unbound local-zone rules."""
    return "".join(
        f'local-zone: "{domain}." always_refuse\n'
        for domain in sorted(domains)
    )


def main():
    source = sys.stdin
    if len(sys.argv) == 2:
        source = open(sys.argv[1], "r", encoding="utf-8", errors="replace")
    elif len(sys.argv) > 2:
        print(f"usage: {sys.argv[0]} [blocklist]", file=sys.stderr)
        return 2

    try:
        try:
            domains = parse_domains(source)
        except ValueError as error:
            print(error, file=sys.stderr)
            return 2
    finally:
        if source is not sys.stdin:
            source.close()

    if not domains:
        print("no supported domains found", file=sys.stderr)
        return 2

    for domain in sorted(domains):
        sys.stdout.write(f'local-zone: "{domain}." always_refuse\n')

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
