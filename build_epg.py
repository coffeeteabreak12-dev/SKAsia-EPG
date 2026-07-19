#!/usr/bin/env python3
from __future__ import annotations

import gzip
import io
import os
import shutil
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = "https://epgshare01.online/epgshare01"
OUTPUT = Path("output")
OUTPUT.mkdir(exist_ok=True)

# Broad regional coverage for the SKAsia catalogue.
FEEDS = [
    "MY1", "SG1", "ID1", "IN1", "UK1", "US2", "CA2", "AU1",
    "HK1", "JP1", "KR1", "TH1", "PH1", "PH2", "PK1", "SA2",
    "DE1", "TW1", "VN1", "BD1", "CN1", "ES1", "EC1", "KZ1",
    "NZ1", "AE1", "FR1", "IT1", "NL1", "PT1", "BR1", "MX1",
]

ACCOUNT_OUTPUTS = [
    "skasia-m240730254672129-epg.xml",
    "skasia-m240730582462128-epg.xml",
]

USER_AGENT = "SKAsia-EPG-GitHub/1.0"

def download_gzip(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=90) as response:
        raw = response.read()
    return gzip.decompress(raw)

def main() -> int:
    root = ET.Element("tv", {
        "generator-info-name": "SKAsia GitHub EPG Merger",
        "generator-info-url": "https://github.com/"
    })

    seen_channels: set[str] = set()
    programme_count = 0
    successful_feeds = 0
    failed: list[str] = []

    for code in FEEDS:
        url = f"{BASE}/epg_ripper_{code}.xml.gz"
        print(f"Downloading {code}: {url}")
        try:
            xml_bytes = download_gzip(url)
            source_root = ET.fromstring(xml_bytes)
        except Exception as exc:
            print(f"WARNING: {code} failed: {exc}", file=sys.stderr)
            failed.append(code)
            continue

        successful_feeds += 1

        for channel in source_root.findall("channel"):
            channel_id = channel.get("id")
            if channel_id and channel_id not in seen_channels:
                root.append(channel)
                seen_channels.add(channel_id)

        for programme in source_root.findall("programme"):
            root.append(programme)
            programme_count += 1

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")

    primary = OUTPUT / ACCOUNT_OUTPUTS[0]
    tree.write(primary, encoding="utf-8", xml_declaration=True)

    # Both SKAsia accounts have the same channel catalogue, so their EPG data is identical.
    second = OUTPUT / ACCOUNT_OUTPUTS[1]
    shutil.copyfile(primary, second)

    # Compressed copies are useful when the XML becomes large.
    for filename in ACCOUNT_OUTPUTS:
        source = OUTPUT / filename
        with source.open("rb") as src, gzip.open(str(source) + ".gz", "wb", compresslevel=9) as dst:
            shutil.copyfileobj(src, dst)

    status = OUTPUT / "build-status.txt"
    status.write_text(
        "\n".join([
            f"Successful feeds: {successful_feeds}",
            f"Failed feeds: {', '.join(failed) if failed else 'None'}",
            f"Unique channel IDs: {len(seen_channels)}",
            f"Programme entries: {programme_count}",
        ]) + "\n",
        encoding="utf-8",
    )

    if successful_feeds == 0:
        raise RuntimeError("All XMLTV downloads failed.")

    print(status.read_text())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
