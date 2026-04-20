#!/usr/bin/env python3
"""Inject COMMUNITY_DATA_INLINE from ifcb_community_structure.json into the HTML.

Usage:
  python3 scripts/inject_community_data.py \
    --data data/ifcb_community_structure.json \
    --html santa-cruz-wharf-timeseries.html
"""
import argparse
import json
import re
from pathlib import Path


def inject_constant(html: str, name: str, payload: object) -> str:
    json_str = json.dumps(payload, separators=(",", ":"))
    new_line = f"const {name} = {json_str};"
    marker_re = re.compile(rf"const {re.escape(name)}\s*=.*?;", re.DOTALL)
    if marker_re.search(html):
        return marker_re.sub(new_line, html)
    # Fall back: insert after first <script> tag
    m = re.search(r"<script[^>]*>", html)
    if not m:
        raise ValueError("No <script> tag found in HTML")
    pos = m.end()
    return html[:pos] + "\n" + new_line + html[pos:]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/ifcb_community_structure.json")
    p.add_argument("--html", default="santa-cruz-wharf-timeseries.html")
    args = p.parse_args()

    data_path = Path(args.data)
    html_path = Path(args.html)

    payload = json.loads(data_path.read_text())
    html = html_path.read_text(encoding="utf-8")

    html = inject_constant(html, "COMMUNITY_DATA_INLINE", payload)
    html_path.write_text(html, encoding="utf-8")

    samples = len(payload.get("samples", []))
    meta = payload.get("metadata", {})
    print(f"Injected COMMUNITY_DATA_INLINE: {samples} samples, {meta.get('start')} → {meta.get('end')}")


if __name__ == "__main__":
    main()
