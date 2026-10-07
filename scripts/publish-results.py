#!/usr/bin/env python3
"""Package explicitly approved, bounded result records; retain original raw runs."""

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_PACKAGE_BYTES = 16 * 1024 * 1024
MAX_ARTIFACTS = 64
TOP_LEVEL = {
    "report.md", "report.json", "benchmark-metadata.json", "campaign.json",
    "attempts.json", "fairness-audit.txt", "fairness-audit.json",
    "loss-ledger.md", "loss-ledger.json", "calibration.json",
}
RESERVED = {"baselines", "releases", "con", "prn", "aux", "nul"}
SECRET_KEYS = {
    "password", "passwd", "secret", "secret_key", "private_key", "api_key",
    "access_token", "refresh_token", "authorization", "connection_string",
}


def linked(path):
    return path.is_symlink() or path.is_junction()


def safe_path(path, boundary=None):
    """Reject symlink/junction ancestry before resolving a bounded path."""
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if linked(part):
            raise ValueError(f"linked path is not publishable: {part}")
    if boundary is not None and not path.is_relative_to(boundary):
        raise ValueError("path escapes its publication boundary")
    return path


def run_name(value):
    if (not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,94}[A-Za-z0-9])?", value)
            or value.split(".")[0].lower() in RESERVED
            or re.fullmatch(r"(?i)(com|lpt)[1-9](?:\..*)?", value)):
        raise ValueError("run ID must be a portable single directory name, not a legacy/reserved name")
    return value


def artifact_name(value):
    if not isinstance(value, str):
        raise TypeError("artifact paths must be strings")
    path = PurePosixPath(value)
    if (path.is_absolute() or str(path) != value or "\\" in value
            or any(p in {".", ".."} for p in path.parts)):
        raise ValueError(f"unsafe artifact path: {value}")
    allowed = (
        value in TOP_LEVEL
        or re.fullmatch(r"[a-z][a-z0-9-]*-(response-shapes|runtime)\.json", value)
        or re.fullmatch(r"system-cards/[a-z][a-z0-9-]*\.json", value)
        or value in {"diagnostics/summary.json", "diagnostics/summary.md"}
    )
    if not allowed:
        raise ValueError(f"artifact is not a curated report/audit/metadata record: {value}")
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_json(data):
    def bad_constant(value):
        raise ValueError(f"non-finite JSON value: {value}")
    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("JSON number exceeds finite floating-point range")
        return parsed
    return json.loads(data, object_pairs_hook=unique_object, parse_constant=bad_constant,
                      parse_float=finite_float)


def read_record(path, boundary=None, limit=MAX_FILE_BYTES):
    path = safe_path(path, boundary)
    for ancestor in path.parents:
        if boundary is not None and ancestor == boundary:
            break
        if boundary is not None and (ancestor / ".git").exists():
            raise ValueError("artifact is inside a working Git checkout")
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
        raise ValueError(f"artifact is not an independent small regular file: {path.name}")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("artifact changed while opening")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("artifact exceeds its size limit")
    safe_path(path, boundary)
    return data


def check_secrets(data, name):
    text = data.decode("utf-8")
    if re.search(r"(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
                 r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
                 r"[a-z][a-z0-9+.-]*://[^/\s]+:[^/@\s]+@)", text):
        raise ValueError(f"possible credential/private key in {name}; curate/redact before approval")
    if name.endswith(".json"):
        parsed = parse_json(text)
        def walk(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    normalized = re.sub(r"[-\s]", "_", key.lower())
                    sensitive = normalized in SECRET_KEYS or re.search(
                        r"(?:^|_)(?:password|passwd|secret|token|api_key|private_key)$", normalized
                    )
                    if sensitive and child not in (None, "", "[redacted]", "***"):
                        raise ValueError(f"credential field in {name}: {key}")
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
            elif isinstance(value, str) and re.search(
                r"(?i)(?:password|pwd|secret|api[_-]?key|access[_-]?token)\s*=\s*[^;\s]+", value
            ):
                raise ValueError(f"credential assignment in {name}")
        walk(parsed)
    elif re.search(r"(?im)^\s*(?:password|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*\S+", text):
        raise ValueError(f"possible credential assignment in {name}")


def raw_run(root, run_id):
    root = safe_path(root)
    directory = safe_path(root / "results" / run_name(run_id), root)
    if (not directory.is_dir() or (directory / ".git").exists()
            or (directory.parent / ".git").exists()):
        raise ValueError("raw run must be an existing results/<run-id>/ directory, not a Git checkout")
    return directory


def collect(root, run_id, names):
    directory = raw_run(root, run_id)
    if not names or len(names) > MAX_ARTIFACTS or len(names) != len(set(names)):
        raise ValueError("select 1-64 distinct curated artifacts")
    records, contents = [], {}
    for name in sorted(names):
        artifact_name(name)
        data = read_record(directory / name, directory)
        check_secrets(data, name)
        records.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        contents[name] = data
    if sum(r["bytes"] for r in records) > MAX_PACKAGE_BYTES:
        raise ValueError("curated package exceeds 16 MiB; raw recordings belong outside Git")
    validate_evidence(directory, contents)
    return records, contents


def validate_evidence(directory, contents):
    required = {"report.md", "report.json"}
    if (directory / "campaign.json").exists():
        required.add("campaign.json")
        if not required <= contents.keys():
            raise ValueError("feature publication requires report.md, report.json and campaign.json")
        report = parse_json(contents["report.json"])
        campaign = parse_json(contents["campaign.json"])
        if (not isinstance(report, dict) or not isinstance(campaign, dict)
                or report.get("valid") is not True or report.get("publishable") is not True
                or report.get("failures") or report.get("publication_failures")
                or campaign.get("mode") != "comparison"):
            raise ValueError("feature campaign publication gates have not passed")
    else:
        required |= {"benchmark-metadata.json", "fairness-audit.txt"}
        if not required <= contents.keys():
            raise ValueError("legacy publication requires reports, benchmark metadata and fairness-audit.txt")
        metadata = parse_json(contents["benchmark-metadata.json"])
        servers = metadata.get("servers") if isinstance(metadata, dict) else None
        if (not isinstance(servers, list) or not servers
                or any(server not in {"honua", "geoserver", "qgis"} for server in servers)):
            raise ValueError("benchmark metadata must identify supported servers")
        for server in servers:
            card = "qgis-server" if server == "qgis" else server
            if f"system-cards/{card}.json" not in contents:
                raise ValueError(f"missing selected copied system card for {server}")
        fairness = contents["fairness-audit.txt"].decode("utf-8")
        if re.search(r"(?m)^FAIL:", fairness) or not re.search(r"(?m)^(PASS|WARN):", fairness):
            raise ValueError("saved fairness audit is failing or does not contain audit evidence")
        report = parse_json(contents["report.json"])
        if not isinstance(report, dict) or report.get("valid") is False or report.get("publishable") is False:
            raise ValueError("report contains a failed publication gate")


def review_plan(root, run_id, names):
    records, _ = collect(root, run_id, names)
    return {
        "schema_version": 1, "run_id": run_id, "decision": "pending",
        "approved_by": None, "approved_at": None, "reference": None,
        "harness_revision": None, "raw_evidence_reference": None,
        "limitations": [], "artifacts": records,
    }


def approval_record(path, run_id):
    data = read_record(path, limit=128 * 1024)
    check_secrets(data, "approval.json")
    approval = parse_json(data)
    if (not isinstance(approval, dict) or approval.get("schema_version") != 1
            or approval.get("run_id") != run_id or approval.get("decision") != "approved"):
        raise ValueError("matching explicit approved decision is required")
    for key in ("approved_by", "approved_at", "reference", "harness_revision"):
        if not isinstance(approval.get(key), str) or not approval[key].strip():
            raise ValueError(f"approval requires {key}")
    moment = datetime.fromisoformat(approval["approved_at"].replace("Z", "+00:00"))
    if moment.tzinfo is None or moment > datetime.now(timezone.utc):
        raise ValueError("approval time must include a timezone and cannot be in the future")
    reference = urlsplit(approval["reference"])
    if reference.scheme != "https" or not reference.netloc or reference.username or reference.password:
        raise ValueError("approval reference must be an HTTPS review record without credentials")
    if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", approval["harness_revision"]):
        raise ValueError("record the original run's full harness commit, not the publisher's current HEAD")
    artifacts = approval.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts or len(artifacts) > MAX_ARTIFACTS:
        raise ValueError("approval must bind selected artifacts and their SHA256s")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise TypeError("approval artifact must be an object")
        artifact_name(artifact.get("path"))
        if not re.fullmatch(r"[0-9a-f]{64}", str(artifact.get("sha256", ""))):
            raise ValueError("each approved artifact requires a SHA256")
    reference = approval.get("raw_evidence_reference")
    if reference is not None:
        if not isinstance(reference, str):
            raise ValueError("raw evidence reference must be an HTTPS archive/review URL or null")
        parsed = urlsplit(reference)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("raw evidence reference must be an HTTPS archive/review URL without credentials")
    if (not isinstance(approval.get("limitations", []), list)
            or any(not isinstance(value, str) for value in approval.get("limitations", []))):
        raise ValueError("limitations must be a list of reviewed caveats")
    return approval


def promote(root, run_id, approval_path, apply=False, before_commit=None):
    root = safe_path(root)
    run_name(run_id)
    approval = approval_record(approval_path, run_id)
    names = [row["path"] for row in approval["artifacts"]]
    records, contents = collect(root, run_id, names)
    approved_hashes = {row["path"]: row["sha256"] for row in approval["artifacts"]}
    if any(row["sha256"] != approved_hashes[row["path"]] for row in records):
        raise ValueError("run artifacts changed after review; obtain fresh approval")
    published = safe_path(root / "published", root)
    if (published / ".git").exists():
        raise ValueError("publication output must not be a working Git checkout")
    destination = safe_path(published / run_id, published)
    if destination.exists():
        raise ValueError("published run already exists; verification never overwrites approval history")
    manifest = {
        "schema_version": 1, "run_id": run_id, "raw_directory": f"results/{run_id}",
        "harness_revision": approval["harness_revision"],
        "approval_reference": approval["reference"],
        "raw_evidence_reference": approval.get("raw_evidence_reference"),
        "artifacts": records, "raw_run_retained": True,
    }
    if not apply:
        return {"mode": "dry-run", "destination": str(destination), "publication": manifest}
    published.mkdir(exist_ok=True)
    # An exclusive run lock prevents concurrent promoters. It is intentionally
    # never stolen on an uncertain prior interruption.
    lock = published / f".{run_id}.publishing"
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    stage = None
    try:
        stage = Path(tempfile.mkdtemp(prefix=f".{run_id}.staging-", dir=published))
        for name, data in contents.items():
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        approval_bytes = (json.dumps(approval, indent=2, allow_nan=False) + "\n").encode()
        manifest["approval_sha256"] = hashlib.sha256(approval_bytes).hexdigest()
        (stage / "approval.json").write_bytes(approval_bytes)
        (stage / "publication.json").write_text(json.dumps(manifest, indent=2) + "\n")
        verify_package(stage, run_id)
        if before_commit:
            before_commit()
        # Re-read the exact approved inputs and safety facts before publishing.
        fresh, _ = collect(root, run_id, names)
        if fresh != records or approval_record(approval_path, run_id) != approval:
            raise ValueError("approval or raw artifacts changed during promotion")
        safe_path(published, root)
        safe_path(destination, published)
        if destination.exists():
            raise ValueError("published destination appeared during promotion")
        stage.rename(destination)
        stage = None
    finally:
        if stage is not None:
            # Only our own random staging directory is removed, never a raw run.
            safe_path(stage, root)
            shutil.rmtree(stage)
        safe_path(lock, root)
        lock.unlink()
    return {"mode": "published", "destination": str(destination), "publication": manifest}


def verify_package(directory, run_id):
    directory = safe_path(directory)
    manifest = parse_json(read_record(directory / "publication.json", directory))
    if not isinstance(manifest, dict):
        raise TypeError("invalid publication manifest")
    approval_bytes = read_record(directory / "approval.json", directory, limit=128 * 1024)
    approval = approval_record(directory / "approval.json", run_id)
    if (manifest.get("schema_version") != 1 or manifest.get("run_id") != run_id
            or manifest.get("raw_directory") != f"results/{run_id}"
            or manifest.get("raw_run_retained") is not True
            or manifest.get("harness_revision") != approval["harness_revision"]
            or manifest.get("approval_reference") != approval["reference"]
            or manifest.get("raw_evidence_reference") != approval.get("raw_evidence_reference")
            or hashlib.sha256(approval_bytes).hexdigest() != manifest.get("approval_sha256")):
        raise ValueError("invalid publication manifest or changed approval record")
    rows = manifest.get("artifacts")
    if not isinstance(rows, list) or not rows or len(rows) > MAX_ARTIFACTS:
        raise ValueError("invalid publication artifact inventory")
    contents = {}
    approved_hashes = {row["path"]: row["sha256"] for row in approval["artifacts"]}
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("invalid publication artifact record")
        name = artifact_name(row.get("path"))
        if name in contents:
            raise ValueError("duplicate publication artifact")
        data = read_record(directory / name, directory)
        check_secrets(data, name)
        digest = hashlib.sha256(data).hexdigest()
        if digest != row.get("sha256") or len(data) != row.get("bytes") or digest != approved_hashes.get(name):
            raise ValueError(f"changed or unapproved published artifact: {name}")
        contents[name] = data
    if set(contents) != set(approved_hashes) or sum(map(len, contents.values())) > MAX_PACKAGE_BYTES:
        raise ValueError("publication inventory does not match the approved small package")
    expected = set(contents) | {"approval.json", "publication.json"}
    expected_directories = {parent.as_posix() for name in expected
                            for parent in PurePosixPath(name).parents if str(parent) != "."}
    actual = set()
    for path in directory.rglob("*"):
        if linked(path):
            raise ValueError("linked entry in publication")
        if path.is_file():
            actual.add(path.relative_to(directory).as_posix())
        elif path.is_dir() and path.relative_to(directory).as_posix() not in expected_directories:
            raise ValueError("unexpected directory in publication")
    if actual != expected:
        raise ValueError("unexpected or missing publication files")
    validate_evidence(directory, contents)
    return {"mode": "verified", "run_id": run_id, "artifacts": len(contents)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="print a pending review plan; never approves or copies a run")
    plan.add_argument("run_id")
    plan.add_argument("--artifact", action="append", required=True)
    publish = commands.add_parser("promote", help="validate explicit approval; dry-run unless --apply")
    publish.add_argument("run_id")
    publish.add_argument("--approval", type=Path, required=True)
    mode = publish.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    verify = commands.add_parser("verify", help="verify an existing immutable approved package")
    verify.add_argument("run_id")
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            result = review_plan(ROOT, run_name(args.run_id), args.artifact)
        elif args.command == "promote":
            result = promote(ROOT, args.run_id, args.approval, args.apply)
        else:
            result = verify_package(safe_path(ROOT / "published" / run_name(args.run_id), ROOT), args.run_id)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Publication refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
