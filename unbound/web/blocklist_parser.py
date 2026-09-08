"""Parse common DNS blocklist formats into safe Unbound local zones."""

import argparse
import ipaddress
import json
import os
import re
import subprocess
import sys
import tempfile


SKIP_DOMAINS = frozenset({
    "localhost", "localhost.localdomain", "local", "broadcasthost",
    "ip6-localhost", "ip6-loopback", "ip6-localnet",
    "ip6-mcastprefix", "ip6-allnodes", "ip6-allrouters", "ip6-allhosts",
})
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_DOMAINS = 500_000
DEFAULT_MAX_AGGREGATE_BYTES = 64 * 1024 * 1024
EXPERT_MAX_BYTES = 64 * 1024 * 1024
EXPERT_MAX_DOMAINS = 3_000_000
EXPERT_MAX_AGGREGATE_BYTES = 256 * 1024 * 1024

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


def iter_domain_actions(lines):
    """Yield block or exclude actions from supported blocklist entries."""
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
                    yield "exclude", domain
                elif is_exception:
                    yield "exclude", domain
                else:
                    yield "block", domain


def parse_domains(lines, max_domains=DEFAULT_MAX_DOMAINS):
    """Parse domains in memory for small callers and tests."""
    domains = set()
    exclusions = set()

    for action, domain in iter_domain_actions(lines):
        if action == "block":
            domains.add(domain)
        else:
            exclusions.add(domain)

    domains -= exclusions
    if len(domains) > max_domains:
        raise ValueError(f"blocklist exceeds the {max_domains} domain limit")

    return domains


def _sort_unique(source_path, output_path):
    env = dict(os.environ, LC_ALL="C")
    temp_dir = os.path.dirname(output_path) or "."
    with open(output_path, "wb") as output:
        subprocess.run(
            ["sort", "-S", "16M", "-T", temp_dir, "-u", source_path],
            stdout=output,
            stderr=subprocess.PIPE,
            check=True,
            env=env,
        )


def _write_difference(domains_path, exclusions_path, output_path, max_domains):
    """Write sorted domains not present in the sorted exclusions file."""
    count = 0
    with (
        open(domains_path, "r", encoding="utf-8") as domains,
        open(exclusions_path, "r", encoding="utf-8") as exclusions,
        open(output_path, "w", encoding="utf-8") as output,
    ):
        excluded = exclusions.readline()
        for domain in domains:
            while excluded and excluded < domain:
                excluded = exclusions.readline()
            if domain == excluded:
                continue
            count += 1
            if count > max_domains:
                raise ValueError(f"blocklist exceeds the {max_domains} domain limit")
            output.write(domain)

    return count


def parse_to_file(lines, output_path, max_domains):
    """Parse and externally sort one source into a normalized domain file."""
    with tempfile.TemporaryDirectory(prefix="unbound-blocklist-parse-") as tmpdir:
        blocks_path = os.path.join(tmpdir, "blocks")
        exclusions_path = os.path.join(tmpdir, "exclusions")

        with (
            open(blocks_path, "w", encoding="utf-8") as blocks,
            open(exclusions_path, "w", encoding="utf-8") as exclusions,
        ):
            for action, domain in iter_domain_actions(lines):
                target = blocks if action == "block" else exclusions
                target.write(f"{domain}\n")

        sorted_blocks_path = os.path.join(tmpdir, "blocks.sorted")
        sorted_exclusions_path = os.path.join(tmpdir, "exclusions.sorted")
        _sort_unique(blocks_path, sorted_blocks_path)
        _sort_unique(exclusions_path, sorted_exclusions_path)

        return _write_difference(
            sorted_blocks_path,
            sorted_exclusions_path,
            output_path,
            max_domains,
        )


def parse_file(input_path, output_path, max_domains):
    with open(input_path, "r", encoding="utf-8", errors="replace") as source:
        return parse_to_file(source, output_path, max_domains)


def compile_config(domains_path, whitelist, output_path, max_domains):
    """Deduplicate parsed domains and stream final Unbound rules to disk."""
    whitelist = {
        domain
        for value in whitelist
        if (domain := normalize_domain(value)) is not None
    }

    with tempfile.TemporaryDirectory(prefix="unbound-blocklist-compile-") as tmpdir:
        sorted_path = os.path.join(tmpdir, "domains.sorted")
        _sort_unique(domains_path, sorted_path)

        count = 0
        with (
            open(sorted_path, "r", encoding="utf-8") as domains,
            open(output_path, "w", encoding="utf-8") as output,
        ):
            for line in domains:
                domain = line.rstrip("\n")
                if not domain or domain in whitelist:
                    continue
                count += 1
                if count > max_domains:
                    raise ValueError(
                        f"combined blocklists exceed the {max_domains} domain limit"
                    )
                output.write(f'local-zone: "{domain}." always_refuse\n')

    return count


def render_unbound_config(domains):
    """Render normalized domains as deterministic Unbound local-zone rules."""
    return "".join(
        f'local-zone: "{domain}." always_refuse\n'
        for domain in sorted(domains)
    )


def _parse_args():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_parser = subparsers.add_parser("parse")
    parse_parser.add_argument("--max-domains", type=int, required=True)
    parse_parser.add_argument("--output", required=True)
    parse_parser.add_argument("input", nargs="?", default="-")

    compile_parser = subparsers.add_parser("compile")
    compile_parser.add_argument("--max-domains", type=int, required=True)
    compile_parser.add_argument("--output", required=True)
    compile_parser.add_argument("--whitelist")
    compile_parser.add_argument("input")

    return parser.parse_args()


def main():
    args = _parse_args()
    try:
        if args.command == "parse":
            if args.input == "-":
                count = parse_to_file(sys.stdin, args.output, args.max_domains)
            else:
                count = parse_file(args.input, args.output, args.max_domains)
            if count == 0:
                raise ValueError("no supported domains found")
        else:
            whitelist = []
            if args.whitelist and os.path.exists(args.whitelist):
                with open(args.whitelist, "r", encoding="utf-8") as source:
                    whitelist = json.load(source)
                if not isinstance(whitelist, list):
                    raise ValueError("whitelist must contain a JSON list")
            count = compile_config(
                args.input,
                whitelist,
                args.output,
                args.max_domains,
            )
            print(count)
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
