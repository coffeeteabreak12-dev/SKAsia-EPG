#!/usr/bin/env python3
from __future__ import annotations

import gzip
import html
import io
import json
import re
import shutil
import sys
import tempfile
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from rapidfuzz import fuzz, process

BASE = "https://epgshare01.online/epgshare01"
OUTPUT = Path("output")
DATA = Path("data")
OUTPUT.mkdir(exist_ok=True)

FEEDS = [
    "MY1", "SG1", "ID1", "IN1", "UK1", "US2", "CA2", "AU1",
    "HK1", "JP1", "KR1", "TH1", "PH1", "PH2", "PK1", "SA2",
    "DE1", "TW1", "VN1", "BD1", "CN1", "ES1", "EC1", "KZ1",
    "NZ1", "AE1", "FR1", "IT1", "NL1", "PT1", "BR1", "MX1",
]

ACCOUNTS = [
    "m240730254672129",
    "m240730582462128",
]

USER_AGENT = "SKAsia-Custom-EPG/4.0"

NOISE_WORDS = {
    "hd", "fhd", "uhd", "4k", "8k", "sd", "hevc", "h265", "h264",
    "live", "backup", "test", "channel", "ch", "tv", "my", "sg", "id",
    "astro", "malaysia", "singapore", "indonesia", "official",
}

def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"\b(?:1080p|720p|576p|50fps|60fps|vip|raw)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    tokens = [t for t in value.split() if t not in NOISE_WORDS]
    return " ".join(tokens)

def region_hint(group: str, name: str) -> str:
    s = f"{group} {name}".lower()
    rules = [
        ("MY1", ["malaysia", "astro", "rtm", "tv3", "8tv", "ntv7", "didik", "bernama"]),
        ("SG1", ["singapore", "mediacorp", "suria", "vasantham", "cna", "channel 5", "channel 8"]),
        ("ID1", ["indonesia", "rcti", "sctv", "indosiar", "antv", "trans7", "trans tv", "mnctv"]),
        ("UK1", ["uk", "bbc", "itv", "sky uk"]),
        ("US2", ["usa", "us:", "hbo usa", "cnn us", "fox news"]),
        ("AU1", ["australia", "abc australia", "sbs"]),
        ("IN1", ["india", "star plus", "sony sab", "zee"]),
        ("HK1", ["hong kong", "tvb", "viutv"]),
        ("JP1", ["japan", "nhk"]),
        ("KR1", ["korea", "kbs", "sbs korea", "mbc korea"]),
        ("TH1", ["thailand", "thai"]),
        ("PH1", ["philippines", "abs-cbn", "gma"]),
    ]
    for code, words in rules:
        if any(word in s for word in words):
            return code
    return ""

def download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as out:
        shutil.copyfileobj(response, out)

def read_channels(feed_path: Path, feed_code: str):
    result = []
    with gzip.open(feed_path, "rb") as fh:
        for event, elem in ET.iterparse(fh, events=("end",)):
            if elem.tag != "channel":
                elem.clear()
                continue
            source_id = elem.get("id", "")
            names = [
                (child.text or "").strip()
                for child in elem.findall("display-name")
                if (child.text or "").strip()
            ]
            if source_id and names:
                result.append({
                    "source_id": source_id,
                    "feed": feed_code,
                    "names": names,
                    "norms": [normalize(n) for n in names if normalize(n)],
                })
            elem.clear()
    return result

def score_match(sk_name: str, sk_group: str, candidate: dict) -> float:
    target = normalize(sk_name)
    if not target:
        return 0.0
    best = 0.0
    for cand in candidate["norms"]:
        if not cand:
            continue
        if target == cand:
            score = 100.0
        else:
            score = max(
                fuzz.WRatio(target, cand),
                fuzz.token_set_ratio(target, cand),
                fuzz.ratio(target, cand),
            )
            if target in cand or cand in target:
                score = max(score, 92.0)
        best = max(best, score)

    hint = region_hint(sk_group, sk_name)
    if hint and candidate["feed"] == hint:
        best += 4.0
    elif hint and candidate["feed"] != hint:
        best -= 4.0
    return min(best, 100.0)

def map_channels(sk_channels: list[dict], source_channels: list[dict]):
    norm_choices = {}
    for idx, candidate in enumerate(source_channels):
        for norm in candidate["norms"]:
            if norm and norm not in norm_choices:
                norm_choices[norm] = idx

    mappings = []
    for pos, sk in enumerate(sk_channels, start=1):
        target = normalize(sk["name"])
        candidate_indices = set()

        if target in norm_choices:
            candidate_indices.add(norm_choices[target])

        # RapidFuzz shortlist keeps matching fast across thousands of channels.
        for _, _, idx in process.extract(
            target,
            norm_choices,
            scorer=fuzz.WRatio,
            limit=12,
            score_cutoff=45,
        ):
            candidate_indices.add(idx)

        best_idx = None
        best_score = 0.0
        for idx in candidate_indices:
            score = score_match(sk["name"], sk["group"], source_channels[idx])
            if score > best_score:
                best_score = score
                best_idx = idx

        # Conservative threshold to prevent incorrect programme guides.
        if best_idx is not None and best_score >= 78.0:
            candidate = source_channels[best_idx]
            mappings.append({
                "sk_name": sk["name"],
                "sk_group": sk["group"],
                "sk_logo": sk.get("logo", ""),
                "source_id": candidate["source_id"],
                "source_feed": candidate["feed"],
                "source_name": candidate["names"][0],
                "score": round(best_score, 2),
            })
        else:
            mappings.append({
                "sk_name": sk["name"],
                "sk_group": sk["group"],
                "sk_logo": sk.get("logo", ""),
                "source_id": "",
                "source_feed": "",
                "source_name": "",
                "score": round(best_score, 2),
            })
    return mappings

def write_custom_xml(account: str, mappings: list[dict], feed_files: dict[str, Path]) -> tuple[int, int]:
    matched = [m for m in mappings if m["source_id"]]
    by_source = defaultdict(list)
    for m in matched:
        by_source[(m["source_feed"], m["source_id"])].append(m)

    out_path = OUTPUT / f"skasia-{account}-epg.xml.gz"
    programme_count = 0

    with gzip.open(out_path, "wt", encoding="utf-8", compresslevel=9) as out:
        out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        out.write('<tv generator-info-name="SKAsia Custom Matched EPG v4">\n')

        # IDs and display names deliberately use the exact SKAsia channel name.
        # IPTVX may use name fallback when the Xtream source has blank EPG IDs.
        for m in matched:
            channel_id = html.escape(m["sk_name"], quote=True)
            out.write(f'  <channel id="{channel_id}">\n')
            out.write(f'    <display-name>{html.escape(m["sk_name"])}</display-name>\n')
            if m["source_name"] != m["sk_name"]:
                out.write(f'    <display-name>{html.escape(m["source_name"])}</display-name>\n')
            if m["sk_logo"]:
                out.write(f'    <icon src="{html.escape(m["sk_logo"], quote=True)}"/>\n')
            out.write('  </channel>\n')

        for feed_code, feed_path in feed_files.items():
            wanted_ids = {
                source_id for (feed, source_id) in by_source
                if feed == feed_code
            }
            if not wanted_ids:
                continue

            with gzip.open(feed_path, "rb") as fh:
                for event, elem in ET.iterparse(fh, events=("end",)):
                    if elem.tag != "programme":
                        elem.clear()
                        continue
                    source_id = elem.get("channel", "")
                    if source_id not in wanted_ids:
                        elem.clear()
                        continue

                    original_xml = ET.tostring(elem, encoding="unicode")
                    for mapping in by_source[(feed_code, source_id)]:
                        replacement = html.escape(mapping["sk_name"], quote=True)
                        rewritten = re.sub(
                            r'channel="[^"]*"',
                            f'channel="{replacement}"',
                            original_xml,
                            count=1,
                        )
                        out.write("  " + rewritten + "\n")
                        programme_count += 1
                    elem.clear()

        out.write("</tv>\n")

    return len(matched), programme_count

def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        feed_files = {}
        all_source_channels = []
        failed = []

        for code in FEEDS:
            url = f"{BASE}/epg_ripper_{code}.xml.gz"
            path = temp / f"{code}.xml.gz"
            print(f"Downloading {code}")
            try:
                download(url, path)
                feed_files[code] = path
                all_source_channels.extend(read_channels(path, code))
            except Exception as exc:
                failed.append(f"{code}: {exc}")
                print(f"WARNING: {code} failed: {exc}", file=sys.stderr)

        if not feed_files:
            raise RuntimeError("No XMLTV feeds could be downloaded.")

        summary_lines = [
            f"Downloaded feeds: {len(feed_files)}",
            f"Source XMLTV channels indexed: {len(all_source_channels)}",
            f"Failed feeds: {len(failed)}",
        ]

        for account in ACCOUNTS:
            catalog_path = DATA / f"channels-{account}.json"
            sk_channels = json.loads(catalog_path.read_text(encoding="utf-8"))
            mappings = map_channels(sk_channels, all_source_channels)

            report_path = OUTPUT / f"mapping-{account}.csv"
            with report_path.open("w", encoding="utf-8", newline="") as report:
                report.write("skasia_channel,group,source_feed,source_channel,score,status\n")
                for m in mappings:
                    fields = [
                        m["sk_name"], m["sk_group"], m["source_feed"],
                        m["source_name"], str(m["score"]),
                        "matched" if m["source_id"] else "unmatched",
                    ]
                    escaped = [
                        '"' + value.replace('"', '""') + '"'
                        for value in fields
                    ]
                    report.write(",".join(escaped) + "\n")

            matched_count, programme_count = write_custom_xml(
                account, mappings, feed_files
            )
            summary_lines.extend([
                "",
                f"Account: {account}",
                f"SKAsia live channels: {len(sk_channels)}",
                f"Matched channels: {matched_count}",
                f"Unmatched channels: {len(sk_channels) - matched_count}",
                f"Written programme entries: {programme_count}",
            ])

        if failed:
            summary_lines.extend(["", "Feed errors:"] + failed)

        (OUTPUT / "build-status.txt").write_text(
            "\n".join(summary_lines) + "\n",
            encoding="utf-8",
        )
        print("\n".join(summary_lines))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
