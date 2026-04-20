# Demo Course Website: bio-oce

Demo course website for a biological oceanography lecture

## Website structure

- `index.html`: main modular site entrypoint
- `assets/css/styles.css`: page styling
- `assets/js/main.js`: interaction, navigation, ENSO and IFCB/CalCOFI data setup
- `data/calcofi_ifcb_sample.json`: sample data payload and schema placeholder for real CalCOFI/IFCB integration
- `syllabus.xlsx`: editable syllabus workbook for updating the course schedule and titles
- `scripts/sync_syllabus_from_xlsx.py`: regenerate the syllabus array in `assets/js/main.js` from `syllabus.xlsx`
- `scripts/populate_sheets.py`: (re)populate the Google Sheet with all site content — run once to reset, or after structural HTML changes

---

## Editing site content via Google Sheets

All text on the Week 13 lecture page is managed through a Google Sheet:
**[bio-oce content sheet](https://docs.google.com/spreadsheets/d/1Rvs8r4QqB01lW3JZZvG3YrEXz79XUbEDAScYhSBXXHY)**

> **Important:** editing the sheet does **not** automatically update the live site. After making edits you must run the sync script (see below) and push the result to GitHub.

### Sheet index — what lives where

| Sheet | What you can edit |
| --- | --- |
| `site_meta` | Nav bar brand text, nav tab labels, section tab labels, course hero title/subtitle, connecting thread |
| `lecture_hero` | Lecture title, subtitle, duration/reading/activity meta items, overview h2 and intro paragraph |
| `summary_table` | The full 12-row overview table — topic name, all 6 columns (physical driver, biological impact, human element, opportunities, challenges), bullet points, and video links |
| `section_headers` | The h2, optional subtitle, and opening intro paragraph for each of the 4 lecture sections |
| `cards` | Every viz card, slide box, and activity card — card title, badge, body text, key concept, activity labels, prompts, and feedback text |
| `resources` | Every tool card and YouTube card — title, description, link text, URL, and video thumbnail alt text. Linked to a card via `card_id`. |

### How the sheets relate to each other

```text
section_headers  ──── section_id ────►  cards  ──── card_id ────►  resources
summary_table    (standalone, keyed by part + topic)
site_meta        (standalone key/value pairs)
lecture_hero     (standalone key/value pairs)
```

- `cards.section_id` matches `section_headers.section_id` (e.g. `section0`, `section1`)
- `resources.card_id` matches `cards.card_id` (e.g. `s2_bio_pump`, `s3_decision_tools`)
- `summary_table` rows are identified by the `part` + `topic` columns — keep these consistent if you reorder rows

---

## How to update the site after editing the sheet

### Step 1 — Edit the sheet

Open the [Google Sheet](https://docs.google.com/spreadsheets/d/1Rvs8r4QqB01lW3JZZvG3YrEXz79XUbEDAScYhSBXXHY) and edit any cell in any sheet.

**Tips:**

- In `summary_table`, the `*_bullets` columns use newlines to separate bullet points — press `Ctrl+Enter` (or `Cmd+Enter` on Mac) inside a cell to insert a newline
- In `resources`, the `video_links_json` column is a JSON array — if you need to add a video link, follow the existing format: `[{"label": "▶ Title", "url": "https://..."}]`
- Don't change the values in `key`, `card_id`, or `resource_id` columns — these are identifiers the sync script uses to find the right place in the HTML. Change the content columns only.
- Don't add or delete rows without also updating `index.html` to match — the sync script updates existing content, it doesn't generate new HTML structure

### Step 2 — Run the sync script

> **One-time prerequisite:** make sure `google-api-python-client` is installed:
>
> ```bash
> pip3 install google-api-python-client google-auth-httplib2 google-auth-oauthlib
> ```
>
> The OAuth token is cached at `/Users/jessiekb/credentials/token.json` after the first run — subsequent runs are silent.

From the repo root:

```bash
python3 scripts/sync_from_sheets.py --credentials /Users/jessiekb/credentials/google-sheets-api.json
```

> **Note:** `sync_from_sheets.py` (the read-direction script) has not been written yet — see [Roadmap](#roadmap) below. For now, edits to the HTML must be made manually by copying updated text from the sheet into `index.html`.

### Step 3 — Preview locally

Open `index.html` directly in a browser, or use a local server:

```bash
python3 -m http.server 8000
# then open http://localhost:8000
```

Check the section you edited — spot-check text, links, and any bullet lists.

### IFCB click-to-bin explorer (local proxy mode)

The Santa Cruz Wharf page now includes an IFCB explorer that needs same-origin API calls.  
Run the helper server instead of `python -m http.server` when using IFCB click-to-bin features:

```bash
python3 scripts/ifcb_proxy.py --port 8000
# then open http://127.0.0.1:8000/santa-cruz-wharf-timeseries.html
```

The helper server:
- serves static site files from the repo root
- exposes `/api/ifcb/*` endpoints used by the chart click workflow
- caches IFCB temp files on demand in `/tmp/bio-oce-ifcb-cache`

### Precompute IFCB community structure (stacked timeseries)

The Santa Cruz Wharf page can render a stacked community structure chart from a static JSON file:

```bash
python3 scripts/build_ifcb_community_structure.py \
  --dataset santa-cruz-municipal-wharf \
  --start 2018-01-01 --end 2026-03-31 \
  --aggregate weekly --top-k 14 --every-nth 20 \
  --output data/ifcb_community_structure.json
```

Notes:
- This is a one-time/offline preprocessing step (fast page load afterward).
- `--every-nth` and `--max-bins` let you run quick tests before a full build.
- Output file is consumed by `santa-cruz-wharf-timeseries.html`.
- This workflow uses autoclass probabilities from `*_class_scores.csv` only (no ROI image downloads).

### Step 4 — Commit and push

```bash
git add index.html
git commit -m "Update lecture content from Google Sheet"
git push
```

If the site is deployed via GitHub Pages, it will go live automatically within ~30 seconds of the push.

---

## Re-populating the sheet from scratch

If the sheet gets accidentally deleted or corrupted, or if you make structural changes to `index.html` and want to reset the sheet to match, run:

```bash
python3 scripts/populate_sheets.py --credentials /Users/jessiekb/credentials/google-sheets-api.json
```

This will **overwrite all sheet content** with the values currently hard-coded in `index.html`. Run this only to reset — it does not read from the HTML, it writes a fixed snapshot.

---

## Syncing the XLSX syllabus

The course schedule (week list on the Syllabus tab) is managed separately via `syllabus.xlsx`, not the Google Sheet.

1. Edit `syllabus.xlsx` in your spreadsheet editor.
2. Run:

   ```bash
   python3 scripts/sync_syllabus_from_xlsx.py
   ```

3. The script updates the syllabus block in `assets/js/main.js` automatically.

---

## Roadmap

- [ ] `scripts/sync_from_sheets.py` — read-direction sync that pulls the Google Sheet and regenerates `index.html` automatically, so manual copy-paste is not needed
- [ ] GitHub Actions workflow to run the sync on every Sheet change (via Apps Script webhook → `repository_dispatch`)
