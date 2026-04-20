#!/usr/bin/env python3
"""Build IFCB community-structure JSON for static visualization.

This script queries IFCB bins, downloads class_scores CSV on demand, maps
classifier labels to taxonomy groups/colors used in this project, aggregates
fractions over time, and writes a compact JSON used by:
  santa-cruz-wharf-timeseries.html

Example:
  python3 scripts/build_ifcb_community_structure.py \
    --dataset santa-cruz-municipal-wharf \
    --start 2018-01-01 --end 2026-03-31 \
    --aggregate weekly --top-k 14 \
    --output data/ifcb_community_structure.json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from json import JSONDecodeError
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REMOTE_ROOT = "https://ifcb.caloos.org"
CACHE_ROOT = Path("/tmp/bio-oce-ifcb-cache/community")

BIN_RE = re.compile(r"^(D\d{8}T\d{6}_IFCB\d+)$")

# Colors aligned with phylogeny/group palette used in the site.
GROUP_COLORS = {
    "Diatom": "#C8BB35",
    "Dinoflagellate": "#B8622A",
    "Cyanobacteria": "#5BA8A0",
    "Coccolithophore": "#5B8DB8",
    "Microzooplankton": "#A45D2A",
    "Flagellate": "#1D9E75",
    "Other/Unmapped": "#7F7F7F",
}

CLASS_MAPPING = {
    "Pseudo-nitzschia": ("Pseudo-nitzschia", "Diatom"),
    "Chaetoceros": ("Chaetoceros", "Diatom"),
    "Skeletonema": ("Skeletonema", "Diatom"),
    "Thalassiosira": ("Thalassiosira", "Diatom"),
    "Thalassionema": ("Thalassionema", "Diatom"),
    "Leptocylindrus": ("Leptocylindrus", "Diatom"),
    "Eucampia": ("Eucampia", "Diatom"),
    "Ditylum": ("Ditylum", "Diatom"),
    "Corethron": ("Corethron", "Diatom"),
    "Licmophora": ("Licmophora", "Diatom"),
    "Odontella": ("Odontella", "Diatom"),
    "Pennate": ("Pennate diatoms", "Diatom"),
    "Centric": ("Centric diatoms", "Diatom"),
    "Det_Cer_Lau": ("Diatom mix (Det/Cer/Lau)", "Diatom"),
    "Ceratium": ("Tripos", "Dinoflagellate"),
    "Alexandrium": ("Alexandrium catenella", "Dinoflagellate"),
    "Cochlodinium": ("Margalefidinium", "Dinoflagellate"),
    "Margalefidinium": ("Margalefidinium", "Dinoflagellate"),
    "Dinophysis": ("Dinophysis", "Dinoflagellate"),
    "Lingulodinium": ("Lingulodinium", "Dinoflagellate"),
    "Prorocentrum": ("Prorocentrum", "Dinoflagellate"),
    "Gymnodinium": ("Gymnodinium", "Dinoflagellate"),
    "Gyrodinium": ("Gyrodinium", "Dinoflagellate"),
    "Akashiwo": ("Akashiwo sanguinea", "Dinoflagellate"),
    "Peridinium": ("Peridinium", "Dinoflagellate"),
    "Scrip_Het": ("Scrippsiella/Heterocapsa", "Dinoflagellate"),
    "Cryptophyte": ("Cryptophyte", "Flagellate"),
    "Mesodinium": ("Mesodinium", "Microzooplankton"),
    "Ciliates": ("Ciliates", "Microzooplankton"),
    "Tintinnid": ("Tintinnid", "Microzooplankton"),
}


@dataclass
class BinInfo:
    bin_id: str
    ts: datetime


def log(msg: str) -> None:
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {msg}", flush=True)


def fetch_bytes(
    url: str,
    timeout: int = 300,
    retries: int = 4,
    backoff_seconds: float = 2.0,
    progress_label: str | None = None,
    progress_every_seconds: float = 2.0,
    allow_404: bool = False,
) -> bytes | None:
    req = Request(url, headers={"User-Agent": "bio-oce-community-builder/1.0"})
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urlopen(req, timeout=timeout) as resp:
                total = resp.headers.get("Content-Length")
                total_int = int(total) if total and total.isdigit() else None
                if progress_label:
                    if total_int:
                        log(f"{progress_label}: starting download ({total_int:,} bytes)")
                    else:
                        log(f"{progress_label}: starting download (unknown size)")

                chunks: list[bytes] = []
                read_bytes = 0
                last_log = time.time()
                while True:
                    chunk = resp.read(1024 * 1024)  # 1 MB chunks
                    if not chunk:
                        break
                    chunks.append(chunk)
                    read_bytes += len(chunk)

                    if progress_label:
                        now = time.time()
                        if now - last_log >= progress_every_seconds:
                            if total_int:
                                pct = 100.0 * read_bytes / max(1, total_int)
                                log(f"{progress_label}: downloaded {read_bytes:,}/{total_int:,} bytes ({pct:.1f}%)")
                            else:
                                log(f"{progress_label}: downloaded {read_bytes:,} bytes")
                            last_log = now

                if progress_label:
                    if total_int:
                        log(f"{progress_label}: completed {read_bytes:,}/{total_int:,} bytes")
                    else:
                        log(f"{progress_label}: completed {read_bytes:,} bytes")
                return b"".join(chunks)
                # Some servers can terminate early without raising during read.
                # Reject partial payloads when Content-Length is known.
                if total_int is not None and read_bytes < total_int:
                    raise RuntimeError(
                        f"Incomplete download: got {read_bytes} of {total_int} bytes"
                    )
        except HTTPError as err:
            if allow_404 and err.code >= 400:
                return None
            last_err = err
            if attempt == retries:
                break
            sleep_s = backoff_seconds * attempt
            log(f"Retrying fetch after error ({attempt}/{retries}): {err}. Sleeping {sleep_s:.1f}s")
            time.sleep(sleep_s)
        except (TimeoutError, URLError, RuntimeError) as err:
            last_err = err
            if attempt == retries:
                break
            sleep_s = backoff_seconds * attempt
            log(f"Retrying fetch after error ({attempt}/{retries}): {err}. Sleeping {sleep_s:.1f}s")
            time.sleep(sleep_s)
    raise RuntimeError(f"Failed to fetch URL after {retries} attempts: {url}") from last_err


def parse_bin_ts(bin_id: str) -> datetime | None:
    m = re.match(r"^D(\d{8})T(\d{6})_IFCB\d+$", bin_id)
    if not m:
        return None
    return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def map_taxon(label: str) -> tuple[str, str, str]:
    for key, (taxon, group) in CLASS_MAPPING.items():
        if label == key or label.startswith(key + "_") or key in label:
            return taxon, group, GROUP_COLORS.get(group, GROUP_COLORS["Other/Unmapped"])
    return label, "Other/Unmapped", GROUP_COLORS["Other/Unmapped"]


def load_bins(
    dataset: str,
    start: date,
    end: date,
    timeout: int,
    retries: int,
    use_cache: bool,
    force_refresh: bool,
) -> list[BinInfo]:
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_ROOT / f"{dataset}_list_bins.json"
    url = f"{REMOTE_ROOT}/api/list_bins?dataset={quote(dataset)}"
    raw: dict[str, Any]

    if use_cache and cache_file.exists() and not force_refresh:
        log(f"Using cached bin list: {cache_file}")
        try:
            raw = json.loads(cache_file.read_text())
        except JSONDecodeError:
            log("Cached bin list is invalid JSON. Refetching from API...")
            force_refresh = True

    if force_refresh or not (use_cache and cache_file.exists() and not force_refresh):
        log(f"Fetching bin list from IFCB API: {url}")
        last_parse_err: Exception | None = None
        for attempt in range(1, retries + 1):
            payload = fetch_bytes(
                url,
                timeout=timeout,
                retries=retries,
                progress_label="list_bins",
            ).decode("utf-8", errors="strict")
            try:
                raw = json.loads(payload)
                if use_cache:
                    cache_file.write_text(json.dumps(raw))
                    log(f"Cached bin list to: {cache_file}")
                break
            except JSONDecodeError as err:
                last_parse_err = err
                if attempt == retries:
                    raise RuntimeError(
                        f"Failed to parse list_bins JSON after {retries} attempts"
                    ) from err
                sleep_s = 1.5 * attempt
                log(f"list_bins JSON parse failed ({attempt}/{retries}): {err}. Retrying in {sleep_s:.1f}s")
                time.sleep(sleep_s)
        else:
            raise RuntimeError("Unexpected failure while loading list_bins") from last_parse_err

    rows = raw.get("data", [])
    log(f"Raw bins from API/cache: {len(rows)}")
    out: list[BinInfo] = []
    for row in rows:
        if isinstance(row, dict):
            bid = str(row.get("pid") or row.get("bin") or "").strip()
        else:
            bid = str(row).strip()
        if not BIN_RE.match(bid):
            continue
        ts = parse_bin_ts(bid)
        if not ts:
            continue
        if start <= ts.date() <= end:
            out.append(BinInfo(bid, ts))
    out.sort(key=lambda x: x.ts)
    log(f"Bins in requested date window: {len(out)}")
    return out


def get_class_scores_csv(
    dataset: str,
    bin_id: str,
    timeout: int,
    retries: int,
    verbose_download: bool = False,
) -> Path | None:
    ddir = CACHE_ROOT / dataset
    ddir.mkdir(parents=True, exist_ok=True)
    local = ddir / f"{bin_id}_class_scores.csv"
    if not local.exists() or local.stat().st_size == 0:
        url = f"{REMOTE_ROOT}/{dataset}/{bin_id}_class_scores.csv"
        if verbose_download:
            log(f"Downloading class_scores for {bin_id}")
        data = fetch_bytes(url, timeout=timeout, retries=retries, allow_404=True)
        if data is None:
            if verbose_download:
                log(f"Skipping {bin_id}: class_scores not found (404)")
            return None
        local.write_bytes(data)
        if verbose_download:
            log(f"Saved: {local}")
    elif verbose_download:
        log(f"Using cached class_scores for {bin_id}")
    return local


def aggregate_key(ts: datetime, mode: str) -> str:
    d = ts.date()
    if mode == "daily":
        return d.isoformat()
    if mode == "monthly":
        return d.replace(day=1).isoformat()
    # weekly (Monday start)
    monday = d - timedelta(days=d.weekday())
    return monday.isoformat()


def build_json(
    bins: list[BinInfo],
    dataset: str,
    aggregate: str,
    top_k: int,
    every_nth: int,
    max_bins: int | None,
    timeout: int,
    retries: int,
    log_every: int,
    verbose_download: bool,
    chunk_weeks: int,
) -> dict[str, Any]:
    selected = bins[:: max(1, every_nth)]
    if max_bins is not None and max_bins > 0:
        selected = selected[:max_bins]
    log(f"Selected {len(selected)} bins after downsampling/cap (every_nth={every_nth}, max_bins={max_bins})")
    if not selected:
        return {
            "dataset": dataset,
            "aggregate": aggregate,
            "top_k": top_k,
            "every_nth": every_nth,
            "max_bins": max_bins,
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "categories": [],
            "samples": [],
            "metadata": {"selected_bins": 0, "input_bins": len(bins), "start": None, "end": None},
        }

    bucket_counts: dict[str, Counter[str]] = defaultdict(Counter)
    bucket_totals: Counter[str] = Counter()
    global_taxa: Counter[str] = Counter()

    def process_bin(b: BinInfo, idx: int) -> None:
        csv_path = get_class_scores_csv(
            dataset,
            b.bin_id,
            timeout=timeout,
            retries=retries,
            verbose_download=verbose_download,
        )
        if csv_path is None:
            if idx == 1 or idx == len(selected) or (idx % max(1, log_every) == 0):
                log(f"Processed {idx}/{len(selected)} bins (latest={b.bin_id}, skipped=404)")
            return
        key = aggregate_key(b.ts, aggregate)

        with csv_path.open(newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader)
            labels = header[1:]
            for row in reader:
                if not row:
                    continue
                vals = []
                for v in row[1 : 1 + len(labels)]:
                    try:
                        vals.append(float(v))
                    except ValueError:
                        vals.append(0.0)
                if not vals:
                    continue
                best_idx = max(range(len(vals)), key=lambda i: vals[i])
                taxon, _group, _color = map_taxon(labels[best_idx])
                bucket_counts[key][taxon] += 1
                bucket_totals[key] += 1
                global_taxa[taxon] += 1

        if idx == 1 or idx == len(selected) or (idx % max(1, log_every) == 0):
            log(f"Processed {idx}/{len(selected)} bins (latest={b.bin_id}, bucket={key})")

    if chunk_weeks > 0:
        span_days = 7 * chunk_weeks
        base_date = selected[0].ts.date()
        chunk_map: dict[date, list[BinInfo]] = defaultdict(list)
        for b in selected:
            delta_days = (b.ts.date() - base_date).days
            chunk_start = base_date + timedelta(days=(delta_days // span_days) * span_days)
            chunk_map[chunk_start].append(b)
        ordered_starts = sorted(chunk_map.keys())
        log(f"Chunked mode enabled: {chunk_weeks}-week windows ({len(ordered_starts)} chunks)")
        idx = 0
        for cstart in ordered_starts:
            cend = cstart + timedelta(days=span_days - 1)
            chunk_bins = chunk_map[cstart]
            log(f"Starting chunk {cstart}..{cend} ({len(chunk_bins)} bins)")
            for b in chunk_bins:
                idx += 1
                process_bin(b, idx)
    else:
        for idx, b in enumerate(selected, start=1):
            process_bin(b, idx)

    top_taxa = [t for t, _ in global_taxa.most_common(max(1, top_k))]
    # Always include key HAB species even if they fall outside top_k
    for _forced in ("Pseudo-nitzschia",):
        if _forced in global_taxa and _forced not in top_taxa:
            top_taxa.append(_forced)
    if "Other/Unmapped" not in top_taxa:
        top_taxa.append("Other/Unmapped")

    categories = []
    for t in top_taxa:
        if t == "Other/Unmapped":
            categories.append({"key": t, "label": t, "color": GROUP_COLORS["Other/Unmapped"]})
            continue
        _mapped, group, color = map_taxon(t)
        categories.append({"key": t, "label": t, "color": color, "group": group})

    samples = []
    for key in sorted(bucket_counts.keys()):
        total = max(1, bucket_totals[key])
        fracs = {}
        other = 0.0
        for taxon, cnt in bucket_counts[key].items():
            f = cnt / total
            if taxon in top_taxa and taxon != "Other/Unmapped":
                fracs[taxon] = fracs.get(taxon, 0.0) + f
            else:
                other += f
        fracs["Other/Unmapped"] = fracs.get("Other/Unmapped", 0.0) + other
        samples.append({"date": key, "fractions": {k: round(fracs.get(k, 0.0), 6) for k in top_taxa}})

    return {
        "dataset": dataset,
        "aggregate": aggregate,
        "top_k": top_k,
        "every_nth": every_nth,
        "max_bins": max_bins,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "categories": categories,
        "samples": samples,
        "metadata": {
            "selected_bins": len(selected),
            "input_bins": len(bins),
            "start": bins[0].ts.date().isoformat() if bins else None,
            "end": bins[-1].ts.date().isoformat() if bins else None,
        },
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build IFCB community structure JSON")
    p.add_argument("--dataset", default="santa-cruz-municipal-wharf")
    p.add_argument("--start", default="2016-08-01", help="YYYY-MM-DD")
    p.add_argument("--end", default=datetime.now().date().isoformat(), help="YYYY-MM-DD")
    p.add_argument("--aggregate", choices=["daily", "weekly", "monthly"], default="weekly")
    p.add_argument("--top-k", type=int, default=14)
    p.add_argument("--every-nth", type=int, default=20, help="Downsample bins for speed (1 = all bins)")
    p.add_argument("--max-bins", type=int, default=0, help="Cap bins for quick tests; 0 means no cap")
    p.add_argument("--timeout", type=int, default=300, help="HTTP timeout in seconds per request")
    p.add_argument("--retries", type=int, default=4, help="HTTP retry attempts")
    p.add_argument("--log-every", type=int, default=10, help="Print progress every N selected bins")
    p.add_argument("--verbose-download", action="store_true", help="Log each class_scores download/cache hit")
    p.add_argument("--chunk-weeks", type=int, default=0, help="Process selected bins in N-week chunks (0 disables chunking)")
    p.add_argument("--no-cache", action="store_true", help="Disable local cache reads/writes")
    p.add_argument("--force-refresh", action="store_true", help="Force refresh of cached list_bins payload")
    p.add_argument("--output", default="data/ifcb_community_structure.json")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    if end < start:
        raise SystemExit("--end must be on/after --start")

    log(
        "Starting build with "
        f"dataset={args.dataset}, range={start}..{end}, aggregate={args.aggregate}, "
        f"top_k={args.top_k}, every_nth={args.every_nth}, max_bins={args.max_bins}, "
        f"timeout={args.timeout}, retries={args.retries}, chunk_weeks={args.chunk_weeks}, "
        f"cache={'off' if args.no_cache else 'on'}"
    )
    log(f"Loading bins for {args.dataset} from {start} to {end}...")
    bins = load_bins(
        dataset=args.dataset,
        start=start,
        end=end,
        timeout=args.timeout,
        retries=args.retries,
        use_cache=not args.no_cache,
        force_refresh=args.force_refresh,
    )
    log(f"Found {len(bins)} bins in range")
    if not bins:
        raise SystemExit("No bins found for selected range")

    payload = build_json(
        bins=bins,
        dataset=args.dataset,
        aggregate=args.aggregate,
        top_k=max(1, args.top_k),
        every_nth=max(1, args.every_nth),
        max_bins=args.max_bins if args.max_bins > 0 else None,
        timeout=args.timeout,
        retries=args.retries,
        log_every=max(1, args.log_every),
        verbose_download=args.verbose_download,
        chunk_weeks=max(0, args.chunk_weeks),
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2))
    log(f"Wrote {out_path} ({len(payload['samples'])} aggregated samples)")


if __name__ == "__main__":
    main()
