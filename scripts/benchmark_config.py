"""Shared track support and release-workflow input validation."""

import os
import re
import sys
from pathlib import Path

CORE_TRACKS = ("attribute-filter", "spatial-bbox", "concurrent")
COMMON_TRACKS = {*CORE_TRACKS, "pagination", "wfs-getfeature", "wms-getmap",
                 "wms-reprojection", "wms-getfeatureinfo"}
FILTERED_TRACKS = {"wfs-filtered", "wms-filtered"}
GSR_TRACKS = {"geoservices-query", "geoservices-query-diagnostics", "geoservices-identify"}
KNOWN_TRACKS = COMMON_TRACKS | FILTERED_TRACKS | GSR_TRACKS | {"wmts", "wcs", "geoservices-export"}


def supports_test(server, test, geoserver_gsr=False):
    if server not in {"honua", "geoserver", "qgis"} or test not in KNOWN_TRACKS:
        raise ValueError(f"Unknown server/test pair: {server}/{test}")
    if test in COMMON_TRACKS:
        return True
    if test in FILTERED_TRACKS:
        return server in {"honua", "geoserver"}
    if test in GSR_TRACKS:
        return server == "honua" or (server == "geoserver" and geoserver_gsr)
    if test in {"wmts", "wcs"}:
        return server == "geoserver"
    return server == "honua"  # geoservices-export


def resolve_workflow_image(env):
    servers = env.get("SERVERS", "honua").split()
    tests = env.get("TESTS", " ".join(CORE_TRACKS)).split()
    if env.get("EVIDENCE_ONLY", "false").lower() != "true" and (
        servers != ["honua"] or len(tests) != len(CORE_TRACKS) or set(tests) != set(CORE_TRACKS)
    ):
        raise ValueError("Custom servers/tracks require evidence_only=true; release gates use Honua core tracks.")

    gsr = env.get("GEOSERVER_GSR_ENABLED", "0") == "1"
    supported_pairs = [supports_test(server, test, gsr) for server in servers for test in tests]
    if not any(supported_pairs):
        raise ValueError("No supported server/test pairs selected.")
    image = env.get("GEOSERVER_IMAGE", "").strip() or (
        "docker.osgeo.org/geoserver:3.0.x" if gsr else "docker.osgeo.org/geoserver:3.0.1"
    )
    if "\n" in image or "\r" in image:
        raise ValueError("GeoServer image must be a single Docker image reference.")
    if gsr and not re.search(r":3\.0\.x(?:@sha256:[0-9a-f]{64})?$", image):
        raise ValueError("GSR requires a matching :3.0.x image, optionally pinned as :3.0.x@sha256:<digest>.")
    return image


def main():
    try:
        if sys.argv[1] == "supports":
            return 0 if supports_test(sys.argv[2], sys.argv[3], sys.argv[4] == "1") else 1
        image = resolve_workflow_image(os.environ)
        with Path(os.environ["GITHUB_ENV"]).open("a") as output:
            output.write(f"GEOSERVER_IMAGE={image}\n")
            output.write(f"HONUA_SELECTED={'true' if 'honua' in os.environ.get('SERVERS', 'honua').split() else 'false'}\n")
        print(f"Validated campaign; GeoServer image: {image}")
        return 0
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
