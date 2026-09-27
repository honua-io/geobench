#!/usr/bin/env python3
"""Record actual image identities and resource limits without container secrets."""

import argparse
import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    server_service = "qgis-server" if args.server == "qgis" else args.server
    services = {}
    for service in (server_service, f"postgis-{args.server}", "k6"):
        container_id = command("docker", "compose", "--profile", args.server, "ps", "-q", service)
        container = json.loads(command("docker", "inspect", container_id))[0]
        image = json.loads(command("docker", "image", "inspect", container["Image"]))[0]
        services[service] = {
            "configured_image": container["Config"]["Image"],
            "image_id": container["Image"],
            "repo_digests": image.get("RepoDigests", []),
            "image_created": image.get("Created"),
            "oci_labels": {key: value for key, value in (image["Config"].get("Labels") or {}).items()
                           if key.startswith("org.opencontainers.image.")},
            "cpus": container["HostConfig"]["NanoCpus"] / 1e9,
            "memory_bytes": container["HostConfig"]["Memory"],
        }
        if service == "geoserver":
            # Extensions are installed at startup and are not covered by the
            # base image digest. Capture every installed JAR's content hash.
            services[service]["jar_sha256"] = command(
                "docker", "exec", container_id, "sh", "-c",
                "find /usr/local/tomcat/webapps/geoserver/WEB-INF/lib -name '*.jar' -exec sha256sum {} +",
            ).splitlines()
    receipt = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "geobench_commit": command("git", "rev-parse", "HEAD"),
        "geobench_dirty": bool(command("git", "status", "--porcelain", "--untracked-files=no")),
        "dataset_sha256": command("sha256sum", "data/small/init.sql").split()[0],
        "host": {"platform": platform.platform(), "logical_cpus": os.cpu_count(),
                 "load_average": os.getloadavg(), "shared_host": True},
        "services": services,
    }
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
