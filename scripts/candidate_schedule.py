#!/usr/bin/env python3
"""Dispatch the per-release Honua benchmark for the release train's pinned candidate.

honua-release pins the honua-server candidate in its public platform-manifest.yaml.
A weekly run always benchmarks that pin; a daily run benchmarks it only when no
earlier per-release run exists for it, so every new release candidate is measured
without a cross-repository token (honua-io/honua-server#8808).
"""
import argparse
import json
import os
import re
import sys
from urllib.request import Request, urlopen

MANIFEST_URL = "https://raw.githubusercontent.com/honua-io/honua-release/trunk/platform-manifest.yaml"
IMAGE_REPOSITORY = "ghcr.io/honua-io/honua-server"
WORKFLOW = "benchmark-on-release.yml"
SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def pinned_candidate(manifest):
    """Return (sha, digest) of components.honua-server without a YAML dependency."""
    block = re.search(r"^components:\n(?:.*\n)*?^  honua-server:\n((?:^(?:    .*|\s*)\n)*)", manifest, re.MULTILINE)
    if not block:
        raise ValueError("manifest has no components.honua-server entry")
    fields = {}
    for line in block.group(1).splitlines():
        match = re.match(r"^    (sha|digest):\s*\"?([^\"#\s]+)\"?", line)
        if match:
            fields.setdefault(match.group(1), match.group(2))
    sha, digest = fields.get("sha", ""), fields.get("digest", "")
    if not SHA.fullmatch(sha) or not DIGEST.fullmatch(digest):
        raise ValueError(f"unexpected honua-server pin: sha={sha!r} digest={digest!r}")
    return sha, digest


def release_tag(sha):
    return f"candidate-{sha[:7]}"


def already_benchmarked(runs, tag):
    """A pin counts as benchmarked once a run for it succeeded or is still running.

    A failed run may never have measured anything (an image not yet pullable, a
    runner fault), so the next daily check dispatches the pin again.
    """
    title = f"Benchmark {tag}"
    return any(run.get("display_title") == title and run.get("conclusion") in {None, "success"}
               for run in runs)


def api(token, path, body=None):
    request = Request(f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}{path}",
                      data=None if body is None else json.dumps(body).encode(),
                      method="GET" if body is None else "POST",
                      headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    with urlopen(request, timeout=30) as response:
        payload = response.read()
    return json.loads(payload) if payload else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--always", action="store_true", help="dispatch even if this pin was benchmarked")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    with urlopen(MANIFEST_URL, timeout=30) as response:
        sha, digest = pinned_candidate(response.read().decode())
    tag, image = release_tag(sha), f"{IMAGE_REPOSITORY}@{digest}"
    token = os.environ["GITHUB_TOKEN"]
    runs = api(token, f"/actions/workflows/{WORKFLOW}/runs?event=workflow_dispatch&per_page=100")["workflow_runs"]
    if not args.always and already_benchmarked(runs, tag):
        print(f"{tag} ({image}) already has a per-release run; nothing to dispatch.")
        return 0
    print(f"Dispatching {WORKFLOW} for {tag}: {image}")
    if not args.dry_run:
        api(token, f"/actions/workflows/{WORKFLOW}/dispatches",
            {"ref": os.environ.get("GITHUB_REF_NAME", "trunk"), "inputs": {"release_tag": tag, "honua_image": image}})
    return 0


if __name__ == "__main__":
    sys.exit(main())
