#!/usr/bin/env python3
"""Generate a deterministic 100K-point PostGIS SQL dump for GeoBench.

Usage: python3 generate.py [--output init.sql] [--count 100000]
"""

import argparse
import math
import os
import random
import string
import sys
from datetime import datetime, timedelta, timezone

SEED = 42
DEFAULT_COUNT = 100_000

CATEGORIES = [
    "park", "building", "road", "bridge", "water",
    "forest", "farm", "commercial", "residential", "industrial",
]
STATUSES = ["active", "inactive", "pending", "archived", "draft"]
COUNTRY_CODES = [
    "US", "US", "US", "US",  # weighted heavier
    "BR", "BR",
    "FR", "DE", "GB", "ES",
    "JP", "JP", "CN", "KR",
    "AU", "AU",
    "IN", "NG", "ZA", "MX",
]

# Geographic hotspots: 60% of points cluster here
HOTSPOTS = [
    (-73.98, 40.75, 2.0),    # NYC area (lon, lat, spread in degrees)
    (2.35, 48.86, 2.0),      # Paris area
    (139.69, 35.69, 2.0),    # Tokyo area
    (-46.63, -23.55, 2.0),   # Sao Paulo area
    (151.21, -33.87, 2.0),   # Sydney area
]

LOREM_WORDS = (
    "spatial data collection infrastructure monitoring environmental "
    "geospatial survey mapping asset feature point polygon terrain "
    "elevation coordinate reference system projection datum layer "
    "service catalog resource metadata attribute schema field type "
    "index query filter spatial temporal analytics dashboard report"
).split()


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def random_point(rng):
    """Generate a point: 60% clustered around hotspots, 40% global."""
    if rng.random() < 0.6:
        lon_c, lat_c, spread = rng.choice(HOTSPOTS)
        lon = lon_c + rng.gauss(0, spread)
        lat = lat_c + rng.gauss(0, spread)
    else:
        lon = rng.uniform(-180, 180)
        lat = rng.uniform(-60, 70)
    lon = clamp(lon, -180, 180)
    lat = clamp(lat, -90, 90)
    return lon, lat


def random_timestamp(rng, start_year=2020, end_year=2025):
    start = datetime(start_year, 1, 1, tzinfo=timezone.utc)
    end = datetime(end_year, 12, 31, tzinfo=timezone.utc)
    delta = (end - start).total_seconds()
    ts = start + timedelta(seconds=rng.uniform(0, delta))
    return ts.strftime("%Y-%m-%d %H:%M:%S+00")


def random_description(rng, min_len=80, max_len=120):
    words = []
    length = 0
    target = rng.randint(min_len, max_len)
    while length < target:
        word = rng.choice(LOREM_WORDS)
        words.append(word)
        length += len(word) + 1
    return " ".join(words)


def escape_copy(value):
    """Escape a string for PostgreSQL COPY format."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def generate(output_path, count):
    rng = random.Random(SEED)

    with open(output_path, "w") as f:
        # Header
        f.write("-- GeoBench: 100K point dataset (deterministic, seed=42)\n")
        f.write(f"-- Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
        f.write(f"-- Features: {count:,}\n\n")

        # Extensions and table
        f.write("CREATE EXTENSION IF NOT EXISTS postgis;\n\n")
        f.write("DROP TABLE IF EXISTS bench_points CASCADE;\n")
        f.write(
            """CREATE TABLE bench_points (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    category        VARCHAR(20) NOT NULL,
    status          VARCHAR(20) NOT NULL,
    priority        INTEGER NOT NULL,
    temperature     DOUBLE PRECISION NOT NULL,
    population      INTEGER NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    country_code    CHAR(2) NOT NULL,
    description     TEXT NOT NULL,
    geom            GEOMETRY(Point, 4326) NOT NULL
);\n\n"""
        )

        # COPY block
        f.write(
            "COPY bench_points "
            "(name, category, status, priority, temperature, population, "
            "created_at, updated_at, country_code, description, geom) "
            "FROM stdin;\n"
        )

        for i in range(1, count + 1):
            name = f"feature_{i}"
            category = rng.choice(CATEGORIES)
            status = rng.choice(STATUSES)
            priority = rng.randint(1, 5)
            temperature = clamp(rng.gauss(15, 12), -20, 50)
            population = clamp(int(math.exp(rng.gauss(8, 2.5))), 0, 10_000_000)
            created_at = random_timestamp(rng)
            # updated_at is 0-365 days after created_at
            created_dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S+00").replace(
                tzinfo=timezone.utc
            )
            updated_dt = created_dt + timedelta(days=rng.uniform(0, 365))
            updated_at = updated_dt.strftime("%Y-%m-%d %H:%M:%S+00")
            country_code = rng.choice(COUNTRY_CODES)
            description = escape_copy(random_description(rng))
            lon, lat = random_point(rng)
            geom = f"SRID=4326;POINT({lon:.6f} {lat:.6f})"

            row = "\t".join(
                [
                    escape_copy(name),
                    category,
                    status,
                    str(priority),
                    f"{temperature:.2f}",
                    str(population),
                    created_at,
                    updated_at,
                    country_code,
                    description,
                    geom,
                ]
            )
            f.write(row + "\n")

            if i % 10000 == 0:
                print(f"  {i:>7,} / {count:,} rows", file=sys.stderr)

        f.write("\\.\n\n")

        # Indexes
        f.write("-- Spatial index\n")
        f.write(
            "CREATE INDEX idx_bench_points_geom ON bench_points USING gist (geom);\n\n"
        )
        f.write("-- Attribute indexes for filter benchmarks\n")
        f.write(
            "CREATE INDEX idx_bench_points_category ON bench_points USING btree (category);\n"
        )
        f.write(
            "CREATE INDEX idx_bench_points_status ON bench_points USING btree (status);\n"
        )
        f.write(
            "CREATE INDEX idx_bench_points_temperature ON bench_points USING btree (temperature);\n"
        )
        f.write(
            "CREATE INDEX idx_bench_points_name ON bench_points USING btree (name varchar_pattern_ops);\n\n"
        )
        f.write("-- Update statistics\n")
        f.write("ANALYZE bench_points;\n")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(
        f"Generated {count:,} features -> {output_path} ({size_mb:.1f} MB)",
        file=sys.stderr,
    )


def main():
    parser = argparse.ArgumentParser(description="Generate GeoBench test dataset")
    parser.add_argument(
        "--output",
        default=os.path.join(os.path.dirname(__file__), "init.sql"),
        help="Output SQL file path (default: data/small/init.sql)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_COUNT,
        help=f"Number of features to generate (default: {DEFAULT_COUNT:,})",
    )
    args = parser.parse_args()
    generate(args.output, args.count)


if __name__ == "__main__":
    main()
