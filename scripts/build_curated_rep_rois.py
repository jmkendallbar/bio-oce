#!/usr/bin/env python3
"""Fetch representative IFCB ROI images and ESD size distributions for each
curated event week and inject them into santa-cruz-wharf-timeseries.html.

Injects two constants:
  CURATED_REP_ROIS_INLINE  — { bin_id: { taxon: {image_url,group,color,confidence} } }
  CURATED_ESD_INLINE       — { bin_id: { group: [esd_um, ...] } }  (sampled from all week bins)

For ESD data, every ROI in every bin of the week is included (confidence ≥ MIN_CONF).
ESD values are EquivDiameter in pixels, which equals microns at 1 px/µm for IFCB104/117.

Usage:
  python3 scripts/build_curated_rep_rois.py
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

REMOTE_ROOT = "https://ifcb.caloos.org"
DATASET = "santa-cruz-municipal-wharf"
REPO_ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = REPO_ROOT / "santa-cruz-wharf-timeseries.html"
CACHE_ROOT = Path("/tmp/bio-oce-ifcb-cache")
MIN_CONF = 0.70
# Sample every Nth bin when collecting ESD data (all bins = too slow; ~20 gives good distributions)
ESD_EVERY_NTH = 15

GROUP_COLORS = {
    "Diatom": "#C8BB35",
    "Dinoflagellate": "#B8622A",
    "Microzooplankton": "#A45D2A",
    "Flagellate": "#1D9E75",
    "Other/Unmapped": "#7F7F7F",
}

CLASS_MAPPING: dict[str, tuple[str, str]] = {
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
    "Guin_Dact": ("Diatom mix (Det/Cer/Lau)", "Diatom"),
    "Pleurosigma": ("Pleurosigma", "Diatom"),
    "Entomoneis": ("Entomoneis", "Diatom"),
    "Tropidoneis": ("Tropidoneis", "Diatom"),
    "Hemiaulus": ("Hemiaulus", "Diatom"),
    "Rhiz_Prob": ("Rhizosolenia", "Diatom"),
    "Asterionellopsis": ("Asterionellopsis", "Diatom"),
    "Cyl_Nitz": ("Cylindrotheca/Nitzschia", "Diatom"),
    "Ceratium": ("Tripos", "Dinoflagellate"),
    "Alexandrium_singlet": ("Alexandrium catenella", "Dinoflagellate"),
    "Alexandrium_spp": ("Alexandrium catenella", "Dinoflagellate"),
    "Alexandrium": ("Alexandrium catenella", "Dinoflagellate"),
    "Cochlodinium": ("Margalefidinium", "Dinoflagellate"),
    "Margalefidinium": ("Margalefidinium", "Dinoflagellate"),
    "Dinophysis": ("Dinophysis", "Dinoflagellate"),
    "Lingulodinium": ("Lingulodinium", "Dinoflagellate"),
    "Prorocentrum": ("Prorocentrum", "Dinoflagellate"),
    "Gymnodinium": ("Gymnodinium", "Dinoflagellate"),
    "Gyrodinium": ("Gymnodinium", "Dinoflagellate"),
    "Akashiwo": ("Akashiwo sanguinea", "Dinoflagellate"),
    "Peridinium": ("Peridinium", "Dinoflagellate"),
    "Scrip_Het": ("Scrippsiella/Heterocapsa", "Dinoflagellate"),
    "Polykrikos": ("Polykrikos", "Dinoflagellate"),
    "Protoperidinium": ("Protoperidinium", "Dinoflagellate"),
    "Torodinium": ("Torodinium", "Dinoflagellate"),
    "Boreadinium": ("Boreadinium", "Dinoflagellate"),
    "Amy_Gony_Protoc": ("Amy/Gony/Protoc", "Dinoflagellate"),
    "Cryptophyte": ("Cryptophyte", "Flagellate"),
    "Ciliates": ("Ciliates", "Microzooplankton"),
    "Tintinnid": ("Tintinnid", "Microzooplankton"),
    "Mesodinium": ("Mesodinium", "Microzooplankton"),
    "Tiarina": ("Tiarina", "Microzooplankton"),
    "Tontonia": ("Tontonia", "Microzooplankton"),
    "NanoP_less10": ("NanoP_less10", "Other/Unmapped"),
    "Clusterflagellate": ("Clusterflagellate", "Other/Unmapped"),
    "FlagMix": ("FlagMix", "Other/Unmapped"),
    "Dictyocha": ("Dictyocha", "Other/Unmapped"),
    "Phaeocystis": ("Phaeocystis", "Other/Unmapped"),
    "Vicicitus": ("Vicicitus", "Other/Unmapped"),
    "Pyramimonas": ("Pyramimonas", "Other/Unmapped"),
}


def map_label(label: str) -> tuple[str, str, str]:
    taxon, group = CLASS_MAPPING.get(label, (label, "Other/Unmapped"))
    color = GROUP_COLORS.get(group, "#7F7F7F")
    return taxon, group, color


def fetch_bytes(url: str, retries: int = 3) -> bytes:
    req = Request(url, headers={"User-Agent": "bio-oce-rep-rois/1.0"})
    for attempt in range(1, retries + 1):
        try:
            with urlopen(req, timeout=60) as resp:
                return resp.read()
        except (HTTPError, URLError) as e:
            if attempt == retries:
                raise
            print(f"  retry {attempt}/{retries} for {url}: {e}")
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def load_all_bins() -> list[str]:
    cache_file = CACHE_ROOT / DATASET / "list_bins.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    if cache_file.exists() and (time.time() - cache_file.stat().st_mtime) < 12 * 3600:
        raw = json.loads(cache_file.read_text())
    else:
        print("Fetching bin list from IFCB API...")
        raw = json.loads(fetch_bytes(f"{REMOTE_ROOT}/api/list_bins?dataset={DATASET}").decode())
        cache_file.write_text(json.dumps(raw))
    rows = raw.get("data", []) if isinstance(raw, dict) else []
    bins = []
    for r in rows:
        bid = r if isinstance(r, str) else (r.get("pid") or r.get("bin") or "")
        if re.match(r"^D\d{8}T\d{6}_IFCB\d+$", bid):
            bins.append(bid)
    print(f"Loaded {len(bins)} total bins")
    return bins


def bins_in_week(all_bins: list[str], event_date: str) -> list[str]:
    d = datetime.strptime(event_date, "%Y-%m-%d")
    week_start = d - timedelta(days=d.weekday())
    week_end = week_start + timedelta(days=7)
    result = []
    for bid in all_bins:
        m = re.match(r"D(\d{8})T", bid)
        if m:
            bdate = datetime.strptime(m.group(1), "%Y%m%d")
            if week_start <= bdate < week_end:
                result.append(bid)
    return result


def fetch_features(bin_id: str) -> dict[int, float]:
    """Return {roi_number: EquivDiameter_um} for a bin."""
    cache_dir = CACHE_ROOT / DATASET / bin_id
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "features.csv"
    if cache_file.exists() and cache_file.stat().st_size > 0:
        csv_text = cache_file.read_text()
    else:
        url = f"{REMOTE_ROOT}/{DATASET}/{bin_id}_features.csv"
        try:
            data = fetch_bytes(url)
        except Exception as e:
            print(f"    features skip {bin_id}: {e}")
            return {}
        cache_file.write_bytes(data)
        csv_text = data.decode("utf-8", errors="replace")

    result = {}
    reader = csv.reader(io.StringIO(csv_text))
    try:
        header = next(reader)
    except StopIteration:
        return {}
    try:
        eq_idx = header.index("EquivDiameter")
    except ValueError:
        return {}
    for row in reader:
        if len(row) <= eq_idx:
            continue
        try:
            roi_num = int(row[0])
            esd = float(row[eq_idx])
            if esd > 0:
                result[roi_num] = round(esd, 2)
        except (ValueError, IndexError):
            continue
    return result


def fetch_class_scores(bin_id: str) -> tuple[list[str], list[tuple[int, str, float]]]:
    """Return (labels, [(roi_number, best_label, best_score), ...]) for a bin."""
    cache_dir = CACHE_ROOT / DATASET / bin_id
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "class_scores.csv"
    if cache_file.exists() and cache_file.stat().st_size > 0:
        csv_text = cache_file.read_text()
    else:
        url = f"{REMOTE_ROOT}/{DATASET}/{bin_id}_class_scores.csv"
        try:
            data = fetch_bytes(url)
        except Exception as e:
            print(f"    class_scores skip {bin_id}: {e}")
            return [], []
        cache_file.write_bytes(data)
        csv_text = data.decode("utf-8", errors="replace")

    reader = csv.reader(io.StringIO(csv_text))
    try:
        header = next(reader)
    except StopIteration:
        return [], []
    labels = header[1:]
    rows = []
    for row in reader:
        if len(row) < 2:
            continue
        pid = row[0].strip()
        m = re.search(r"_(\d+)$", pid)
        if not m:
            continue
        roi_num = int(m.group(1))
        scores = [float(v) if v else 0.0 for v in row[1:]]
        if not scores:
            continue
        best_idx = scores.index(max(scores))
        best_score = scores[best_idx]
        if best_score >= MIN_CONF:
            rows.append((roi_num, labels[best_idx], best_score, pid))
    return labels, rows


def scan_bin_for_rois(
    bin_id: str,
    best_rois: dict[str, dict],
    target_taxa: set[str],
    esd_by_group: dict[str, list[float]],
    collect_esd: bool,
) -> None:
    """Update best_rois and esd_by_group from one bin."""
    _, cs_rows = fetch_class_scores(bin_id)
    if not cs_rows:
        return

    feats: dict[int, float] = {}
    if collect_esd:
        feats = fetch_features(bin_id)

    for roi_num, label, score, pid in cs_rows:
        taxon, group, color = map_label(label)

        # Update best rep image
        if taxon in target_taxa:
            if taxon not in best_rois or score > best_rois[taxon]["confidence"]:
                best_rois[taxon] = {
                    "image_url": f"https://ifcb.caloos.org/{DATASET}/{pid}.png",
                    "group": group,
                    "color": color,
                    "confidence": round(score, 4),
                }

        # Collect ESD
        if collect_esd and roi_num in feats:
            esd_by_group.setdefault(group, []).append(feats[roi_num])


def process_week(
    event_date: str,
    primary_bin: str,
    target_taxa: set[str],
    all_bins: list[str],
) -> tuple[dict[str, dict], dict[str, list[float]]]:
    """Return (best_rois, esd_by_group) for the event's week."""
    week_bins = bins_in_week(all_bins, event_date)
    week_bins = [primary_bin] + [b for b in week_bins if b != primary_bin]
    print(f"  {len(week_bins)} bins in week of {event_date}")

    best_rois: dict[str, dict] = {}
    esd_by_group: dict[str, list[float]] = {}

    # Phase 1: scan bins until all taxa covered (sequential, stop early)
    for i, bin_id in enumerate(week_bins):
        missing = target_taxa - best_rois.keys()
        if not missing:
            print(f"  rep images: all {len(target_taxa)} taxa covered after {i} bins")
            break
        scan_bin_for_rois(bin_id, best_rois, target_taxa, esd_by_group, collect_esd=True)
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(week_bins)} bins, {len(best_rois)}/{len(target_taxa)} taxa")
    else:
        print(f"  rep images: scanned all {len(week_bins)} bins, {len(best_rois)}/{len(target_taxa)} taxa")

    missing = target_taxa - best_rois.keys()
    if missing:
        print(f"  no rep image found for: {sorted(missing)}")

    # Phase 2: sample remaining bins for ESD only (every Nth)
    covered_up_to = min(len(week_bins), next(
        (i + 1 for i, b in enumerate(week_bins) if not (target_taxa - best_rois.keys())),
        len(week_bins)
    ))
    esd_bins = week_bins[covered_up_to::ESD_EVERY_NTH]
    if esd_bins:
        print(f"  ESD: sampling {len(esd_bins)} additional bins (every {ESD_EVERY_NTH}th of remaining {len(week_bins)-covered_up_to})")
    for i, bin_id in enumerate(esd_bins):
        scan_bin_for_rois(bin_id, best_rois, set(), esd_by_group, collect_esd=True)
        if (i + 1) % 5 == 0:
            total = sum(len(v) for v in esd_by_group.values())
            print(f"  ESD: {i+1}/{len(esd_bins)} bins, {total} ROIs collected")

    total_esd = sum(len(v) for v in esd_by_group.values())
    for grp, esds in sorted(esd_by_group.items()):
        print(f"  ESD {grp}: {len(esds)} ROIs, range {min(esds):.1f}–{max(esds):.1f} µm")
    print(f"  ESD total: {total_esd} ROIs")

    # Round ESD values to 1 decimal to reduce JSON size
    esd_by_group = {g: [round(v, 1) for v in vs] for g, vs in esd_by_group.items()}
    return best_rois, esd_by_group


def extract_curated_events(html: str) -> list[dict]:
    m = re.search(r"const CURATED_EVENTS_INLINE\s*=\s*(\[.*?\]);", html, re.DOTALL)
    if not m:
        raise ValueError("CURATED_EVENTS_INLINE not found in HTML")
    return json.loads(m.group(1))


def extract_community_taxa_for_week(html: str, event_date: str) -> set[str]:
    m = re.search(r"const COMMUNITY_DATA_INLINE\s*=\s*(\{.*?\});(?=\s*\n)", html, re.DOTALL)
    if not m:
        return set()
    data = json.loads(m.group(1))
    samples = data.get("samples", [])
    if not samples:
        return set()
    target = datetime.strptime(event_date, "%Y-%m-%d")
    best_sample = min(samples, key=lambda s: abs(datetime.strptime(s["date"], "%Y-%m-%d") - target))
    fractions = best_sample.get("fractions", {})
    return {t for t, v in fractions.items() if isinstance(v, float) and v > 0 and t != "Other/Unmapped"}


def inject_constant(html: str, name: str, payload: object) -> str:
    json_str = json.dumps(payload, separators=(",", ":"))
    new_line = f"const {name} = {json_str};"
    marker_re = re.compile(rf"const {re.escape(name)}\s*=.*?;", re.DOTALL)
    if marker_re.search(html):
        return marker_re.sub(new_line, html)
    # Insert after CURATED_EVENTS_INLINE
    curated_re = re.compile(r"(const CURATED_EVENTS_INLINE\s*=.*?;)", re.DOTALL)
    m = curated_re.search(html)
    if not m:
        raise ValueError("Could not find insertion point in HTML")
    return html[: m.end()] + "\n" + new_line + html[m.end():]


def main() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    events = extract_curated_events(html)
    all_bins = load_all_bins()

    rois_payload: dict[str, dict] = {}
    esd_payload: dict[str, dict] = {}

    for ev in events:
        event_id = ev["id"]
        bin_id = ev["bin_id"]
        event_date = ev["date"]
        print(f"\nProcessing {event_id} / {bin_id} (week of {event_date})...")
        target_taxa = extract_community_taxa_for_week(html, event_date)
        print(f"  target taxa: {sorted(target_taxa)}")
        try:
            best_rois, esd_by_group = process_week(event_date, bin_id, target_taxa, all_bins)
            rois_payload[bin_id] = best_rois
            esd_payload[bin_id] = esd_by_group
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"  ERROR: {e}")
            rois_payload[bin_id] = {}
            esd_payload[bin_id] = {}

    html = inject_constant(html, "CURATED_REP_ROIS_INLINE", rois_payload)
    html = inject_constant(html, "CURATED_ESD_INLINE", esd_payload)
    HTML_PATH.write_text(html, encoding="utf-8")

    total_rois = sum(len(v) for v in rois_payload.values())
    total_esd = sum(sum(len(vs) for vs in v.values()) for v in esd_payload.values())
    print(f"\nInjected CURATED_REP_ROIS_INLINE ({total_rois} taxa) and CURATED_ESD_INLINE ({total_esd} ESD values)")


if __name__ == "__main__":
    main()
