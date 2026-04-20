#!/usr/bin/env python3
"""Local static + IFCB helper API server for the Santa Cruz Wharf explorer.

Usage:
  python3 scripts/ifcb_proxy.py --port 8000
Then open:
  http://localhost:8000/santa-cruz-wharf-timeseries.html
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from statistics import pvariance
from typing import Any
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

DATASET_DEFAULT = "santa-cruz-municipal-wharf"
REMOTE_ROOT = "https://ifcb.caloos.org"
CACHE_TTL_SECONDS = 12 * 60 * 60
CACHE_ROOT = Path("/tmp/bio-oce-ifcb-cache")
REPO_ROOT = Path(__file__).resolve().parents[1]

BIN_RE = re.compile(r"^(D\d{8}T\d{6}_IFCB\d+)$")
PID_RE = re.compile(r"^(D\d{8}T\d{6}_IFCB\d+_\d+)$")
DATASET_RE = re.compile(r"^[a-z0-9\-]+$")

FEATURE_CANDIDATES = [
    "Area",
    "Biovolume",
    "MajorAxisLength",
    "MinorAxisLength",
    "Eccentricity",
    "EquivDiameter",
    "Perimeter",
    "Solidity",
    "SurfaceArea",
    "texture_entropy",
    "texture_average_contrast",
    "RepresentativeWidth",
    "maxFeretDiameter",
    "minFeretDiameter",
    "Area_over_Perimeter",
    "Area_over_PerimeterSquared",
]

# IFCB class aliases -> taxa/groups used across the project and notebook/phylogeny naming.
CLASS_MAPPING = {
    "Pseudo-nitzschia": ("Pseudo-nitzschia", "Diatom", "#4B7AD8"),
    "Chaetoceros": ("Chaetoceros", "Diatom", "#4B7AD8"),
    "Dinophysis": ("Dinophysis", "Dinoflagellate", "#185FA5"),
    "Ceratium": ("Tripos", "Dinoflagellate", "#185FA5"),
    "Cochlodinium": ("Margalefidinium", "Dinoflagellate", "#185FA5"),
    "Alexandrium_singlet": ("Alexandrium catenella", "Dinoflagellate", "#185FA5"),
    "Alexandrium_spp": ("Alexandrium catenella", "Dinoflagellate", "#185FA5"),
    "Lingulodinium": ("Lingulodinium", "Dinoflagellate", "#185FA5"),
    "Prorocentrum": ("Prorocentrum", "Dinoflagellate", "#185FA5"),
    "Skeletonema": ("Skeletonema", "Diatom", "#4B7AD8"),
    "Det_Cer_Lau": ("Diatom mix (Det/Cer/Lau)", "Diatom", "#4B7AD8"),
    "Thalassiosira": ("Thalassiosira", "Diatom", "#4B7AD8"),
    "Thalassionema": ("Thalassionema", "Diatom", "#4B7AD8"),
    "Leptocylindrus": ("Leptocylindrus", "Diatom", "#4B7AD8"),
    "Eucampia": ("Eucampia", "Diatom", "#4B7AD8"),
    "Ditylum": ("Ditylum", "Diatom", "#4B7AD8"),
    "Licmophora": ("Licmophora", "Diatom", "#4B7AD8"),
    "Corethron": ("Corethron", "Diatom", "#4B7AD8"),
    "Odontella": ("Odontella", "Diatom", "#4B7AD8"),
    "Pennate": ("Pennate diatoms", "Diatom", "#4B7AD8"),
    "Centric": ("Centric diatoms", "Diatom", "#4B7AD8"),
    "Cryptophyte": ("Cryptophyte", "Flagellate", "#1D9E75"),
    "Ciliates": ("Ciliates", "Microzooplankton", "#A45D2A"),
    "Tintinnid": ("Tintinnid", "Microzooplankton", "#A45D2A"),
    "Mesodinium": ("Mesodinium", "Ciliate", "#A45D2A"),
    "Akashiwo": ("Akashiwo sanguinea", "Dinoflagellate", "#185FA5"),
}


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def parse_bin_timestamp(bin_id: str) -> datetime | None:
    m = re.match(r"^D(\d{8})T(\d{6})_IFCB\d+$", bin_id)
    if not m:
        return None
    return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def map_taxon(label: str) -> tuple[str, str, str]:
    for key, mapped in CLASS_MAPPING.items():
        if label == key or label.startswith(key + "_") or key in label:
            return mapped
    return (label, "Other/Unmapped", "#7F7F7F")


def safe_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def fetch_bytes(url: str, timeout: int = 60) -> bytes:
    req = Request(url, headers={"User-Agent": "bio-oce-ifcb-proxy/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def cache_dir(dataset: str, bin_id: str | None = None) -> Path:
    base = CACHE_ROOT / dataset
    if bin_id:
        return base / bin_id
    return base


def ensure_dataset(dataset: str) -> str:
    if not DATASET_RE.match(dataset):
        raise ValueError("Invalid dataset")
    return dataset


def load_bins(dataset: str) -> list[dict[str, Any]]:
    dataset = ensure_dataset(dataset)
    ddir = cache_dir(dataset)
    ddir.mkdir(parents=True, exist_ok=True)
    cache_file = ddir / "list_bins.json"

    raw_payload: dict[str, Any]
    use_cached = False
    if cache_file.exists() and (time.time() - cache_file.stat().st_mtime) < CACHE_TTL_SECONDS:
        raw_payload = json.loads(cache_file.read_text())
        use_cached = True
    else:
        url = f"{REMOTE_ROOT}/api/list_bins?dataset={quote(dataset)}"
        raw_payload = json.loads(fetch_bytes(url).decode("utf-8"))
        cache_file.write_text(json.dumps(raw_payload))

    rows = raw_payload.get("data", []) if isinstance(raw_payload, dict) else []
    bins: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            bin_id = str(row.get("pid") or row.get("bin") or "").strip()
        else:
            bin_id = str(row).strip()
        ts = parse_bin_timestamp(bin_id)
        if not ts:
            continue
        bins.append(
            {
                "bin": bin_id,
                "timestamp": ts.isoformat().replace("+00:00", "Z"),
                "epoch": ts.timestamp(),
            }
        )
    bins.sort(key=lambda x: x["epoch"])
    return [{"cached": use_cached, "count": len(bins)}, *bins]


def resolve_bin(dataset: str, date_text: str) -> dict[str, Any]:
    bins_wrapped = load_bins(dataset)
    meta = bins_wrapped[0]
    bins = bins_wrapped[1:]
    if not bins:
        raise ValueError("No bins found for dataset")
    target_date = datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    target_noon = target_date.replace(hour=12)

    def dist_seconds(item: dict[str, Any]) -> float:
        return abs(item["epoch"] - target_noon.timestamp())

    same_day = [b for b in bins if datetime.fromtimestamp(b["epoch"], tz=timezone.utc).date() == target_date.date()]
    candidates = same_day if same_day else bins
    best = min(candidates, key=dist_seconds)
    best_dt = datetime.fromtimestamp(best["epoch"], tz=timezone.utc)

    return {
        "dataset": dataset,
        "target_date": date_text,
        "bin": best["bin"],
        "bin_timestamp": best["timestamp"],
        "same_day_match": bool(same_day),
        "distance_hours": round(dist_seconds(best) / 3600.0, 3),
        "timeline_url": f"{REMOTE_ROOT}/timeline?dataset={quote(dataset)}&bin={quote(best['bin'])}",
        "bins_cached": bool(meta.get("cached")),
        "bins_count": int(meta.get("count", 0)),
        "resolved_at": utc_now_iso(),
        "target_timestamp_utc": target_noon.isoformat().replace("+00:00", "Z"),
        "bin_date": best_dt.strftime("%Y-%m-%d"),
    }


def ensure_bin_files(dataset: str, bin_id: str) -> dict[str, str]:
    if not BIN_RE.match(bin_id):
        raise ValueError("Invalid bin ID")
    dataset = ensure_dataset(dataset)
    bdir = cache_dir(dataset, bin_id)
    bdir.mkdir(parents=True, exist_ok=True)

    status: dict[str, str] = {}
    files = {
        "class_scores": (f"{bin_id}_class_scores.csv", bdir / "class_scores.csv"),
        "features": (f"{bin_id}_features.csv", bdir / "features.csv"),
    }

    for key, (remote_name, local_path) in files.items():
        if local_path.exists() and local_path.stat().st_size > 0:
            status[key] = "cached"
            continue
        remote_url = f"{REMOTE_ROOT}/{dataset}/{remote_name}"
        tmp_fd, tmp_name = tempfile.mkstemp(prefix=f"ifcb-{key}-", suffix=".tmp")
        try:
            with open(tmp_fd, "wb", closefd=True) as fh:
                fh.write(fetch_bytes(remote_url))
            Path(tmp_name).replace(local_path)
            status[key] = "downloaded"
        finally:
            if Path(tmp_name).exists():
                Path(tmp_name).unlink(missing_ok=True)

    return status


def build_bin_bundle(dataset: str, bin_id: str, min_conf: float = 0.9, limit: int = 200) -> dict[str, Any]:
    download_status = ensure_bin_files(dataset, bin_id)
    bdir = cache_dir(dataset, bin_id)
    class_csv = bdir / "class_scores.csv"
    feat_csv = bdir / "features.csv"

    class_rows: dict[int, dict[str, Any]] = {}
    class_counts: Counter[str] = Counter()
    conf_sum: defaultdict[str, float] = defaultdict(float)

    with class_csv.open(newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        labels = header[1:]
        for row in reader:
            if not row:
                continue
            pid = row[0]
            pm = re.search(r"_(\d+)$", pid)
            if not pm:
                continue
            roi_num = int(pm.group(1))
            probs = [safe_float(v) or 0.0 for v in row[1 : 1 + len(labels)]]
            if not probs:
                continue
            best_idx, best_prob = max(enumerate(probs), key=lambda x: x[1])
            raw_label = labels[best_idx]
            mapped_taxon, mapped_group, mapped_color = map_taxon(raw_label)
            class_rows[roi_num] = {
                "pid": pid,
                "raw_label": raw_label,
                "mapped_taxon": mapped_taxon,
                "mapped_group": mapped_group,
                "chip_color": mapped_color,
                "confidence": best_prob,
            }
            class_counts[mapped_taxon] += 1
            conf_sum[mapped_taxon] += best_prob

    feature_rows: list[dict[str, Any]] = []
    representative_by_taxon: dict[str, dict[str, Any]] = {}
    feature_values_by_class: defaultdict[str, defaultdict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    with feat_csv.open(newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            roi_val = row.get("roi_number")
            roi_num = int(float(roi_val)) if roi_val else None
            if roi_num is None or roi_num not in class_rows:
                continue
            cmeta = class_rows[roi_num]
            area = safe_float(row.get("Area")) or 0.0
            out = {
                "roi_number": roi_num,
                "area": area,
                "pid": cmeta["pid"],
                "raw_label": cmeta["raw_label"],
                "mapped_taxon": cmeta["mapped_taxon"],
                "mapped_group": cmeta["mapped_group"],
                "chip_color": cmeta["chip_color"],
                "confidence": round(cmeta["confidence"], 4),
                "image_url": f"/api/ifcb/roi_image?dataset={quote(dataset)}&pid={quote(cmeta['pid'])}",
            }
            feature_rows.append(out)
            current = representative_by_taxon.get(cmeta["mapped_taxon"])
            if (
                current is None
                or out["confidence"] > current["confidence"]
                or (
                    out["confidence"] == current["confidence"]
                    and out["area"] > current["area"]
                )
            ):
                representative_by_taxon[cmeta["mapped_taxon"]] = out

            if cmeta["confidence"] >= min_conf:
                cls = cmeta["mapped_taxon"]
                for feat in FEATURE_CANDIDATES:
                    v = safe_float(row.get(feat))
                    if v is not None and math.isfinite(v):
                        feature_values_by_class[feat][cls].append(v)

    feature_rows.sort(key=lambda r: r["area"], reverse=True)
    top_rows = feature_rows[: max(1, min(limit, 1500))]

    top_taxa = []
    for taxon, count in class_counts.most_common(10):
        avg_conf = conf_sum[taxon] / count
        top_taxa.append({"taxon": taxon, "count": int(count), "avg_confidence": round(avg_conf, 4)})

    representative_rois: list[dict[str, Any]] = []
    for taxon, count in class_counts.most_common(200):
        rep = representative_by_taxon.get(taxon)
        if not rep:
            continue
        representative_rois.append(
            {
                "taxon": taxon,
                "count": int(count),
                "pid": rep["pid"],
                "mapped_group": rep["mapped_group"],
                "chip_color": rep["chip_color"],
                "confidence": rep["confidence"],
                "area": rep["area"],
                "image_url": rep["image_url"],
            }
        )

    feature_scores: list[dict[str, Any]] = []
    for feat, by_class in feature_values_by_class.items():
        class_means = {k: sum(v) / len(v) for k, v in by_class.items() if len(v) >= 3}
        if len(class_means) < 2:
            continue
        score = pvariance(class_means.values())
        if not math.isfinite(score):
            continue
        feature_scores.append(
            {
                "feature": feat,
                "between_class_variance": round(score, 6),
                "class_count": len(class_means),
                "means": [{"taxon": k, "mean": round(v, 6)} for k, v in sorted(class_means.items(), key=lambda x: x[1], reverse=True)[:6]],
            }
        )

    feature_scores.sort(key=lambda x: x["between_class_variance"], reverse=True)

    return {
        "dataset": dataset,
        "bin": bin_id,
        "download_status": download_status,
        "rows_total": len(feature_rows),
        "rows_returned": len(top_rows),
        "min_conf": min_conf,
        "limit": limit,
        "top_taxa": top_taxa,
        "representative_rois": representative_rois,
        "feature_ranking": feature_scores[:15],
        "rois": top_rows,
        "generated_at": utc_now_iso(),
    }


class IFCBProxyHandler(SimpleHTTPRequestHandler):
    server_version = "BioOceIFCBProxy/1.0"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, directory=str(REPO_ROOT), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/ifcb/"):
            self.handle_ifcb_api(parsed)
            return
        super().do_GET()

    def handle_ifcb_api(self, parsed: Any) -> None:
        query = parse_qs(parsed.query)
        dataset = query.get("dataset", [DATASET_DEFAULT])[0]

        try:
            if parsed.path == "/api/ifcb/list_bins":
                data = load_bins(dataset)
                payload = {
                    "dataset": dataset,
                    "meta": data[0] if data else {},
                    "bins": data[1:] if len(data) > 1 else [],
                    "generated_at": utc_now_iso(),
                }
                self.send_json(payload)
                return

            if parsed.path == "/api/ifcb/resolve_bin":
                date_text = query.get("date", [""])[0]
                if not date_text:
                    self.send_json({"error": "Missing date=YYYY-MM-DD"}, status=HTTPStatus.BAD_REQUEST)
                    return
                self.send_json(resolve_bin(dataset, date_text))
                return

            if parsed.path == "/api/ifcb/bin_bundle":
                bin_id = query.get("bin", [""])[0]
                if not bin_id:
                    self.send_json({"error": "Missing bin"}, status=HTTPStatus.BAD_REQUEST)
                    return
                min_conf = float(query.get("min_conf", ["0.9"])[0])
                limit = int(query.get("limit", ["200"])[0])
                payload = build_bin_bundle(dataset, bin_id, min_conf=min_conf, limit=limit)
                self.send_json(payload)
                return

            if parsed.path == "/api/ifcb/roi_image":
                pid = query.get("pid", [""])[0]
                self.serve_roi_image(dataset, pid)
                return

            self.send_json({"error": "Unknown IFCB endpoint"}, status=HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001
            self.send_json({"error": f"Proxy failure: {exc}"}, status=HTTPStatus.BAD_GATEWAY)

    def serve_roi_image(self, dataset: str, pid: str) -> None:
        dataset = ensure_dataset(dataset)
        if not PID_RE.match(pid):
            self.send_json({"error": "Invalid pid"}, status=HTTPStatus.BAD_REQUEST)
            return

        bin_id = pid.rsplit("_", 1)[0]
        bdir = cache_dir(dataset, bin_id)
        bdir.mkdir(parents=True, exist_ok=True)
        local_img = bdir / f"{pid}.png"
        if not local_img.exists():
            remote_url = f"{REMOTE_ROOT}/{dataset}/{pid}.png"
            local_img.write_bytes(fetch_bytes(remote_url))

        body = local_img.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run local static+IFCB helper server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), IFCBProxyHandler)
    print(f"Serving {REPO_ROOT} at http://{args.host}:{args.port}")
    print("IFCB API available at /api/ifcb/*")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
