#!/usr/bin/env python3
"""
Populate the bio-oce course Google Sheet with all editable website content.

Spreadsheet: https://docs.google.com/spreadsheets/d/1Rvs8r4QqB01lW3JZZvG3YrEXz79XUbEDAScYhSBXXHY

Sheets created:
  1. site_meta        — nav bar, course hero, section tab labels
  2. lecture_hero     — lecture page header fields
  3. summary_table    — 12-row topic table (Intro through Part V)
  4. section_headers  — h2 / subtitle / intro paragraph per section
  5. cards            — every viz card, slide-box part, activity card
  6. resources        — tool cards, YouTube cards, video links (linked to cards via card_id)

Run:
  python3 scripts/populate_sheets.py --credentials /path/to/credentials.json

OAuth credentials: download a Desktop OAuth 2.0 client JSON from
  https://console.cloud.google.com/apis/credentials
and pass the path with --credentials.  On first run a browser window
will open for consent; the token is cached in token.json alongside the
credentials file so subsequent runs are silent.
"""

import argparse
import json
import os
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SPREADSHEET_ID = "1Rvs8r4QqB01lW3JZZvG3YrEXz79XUbEDAScYhSBXXHY"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_credentials(credentials_path: str) -> Credentials:
    token_path = os.path.join(os.path.dirname(credentials_path), "token.json")
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return creds


# ---------------------------------------------------------------------------
# Sheet helpers
# ---------------------------------------------------------------------------

def get_existing_sheet_ids(service) -> dict[str, int]:
    meta = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    return {s["properties"]["title"]: s["properties"]["sheetId"]
            for s in meta.get("sheets", [])}


def ensure_sheets(service, names: list[str]) -> dict[str, int]:
    """Create any sheets that don't exist yet; return title→sheetId map."""
    existing = get_existing_sheet_ids(service)
    requests = []
    for name in names:
        if name not in existing:
            requests.append({"addSheet": {"properties": {"title": name}}})
    if requests:
        resp = service.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID, body={"requests": requests}
        ).execute()
        for reply in resp.get("replies", []):
            props = reply.get("addSheet", {}).get("properties", {})
            if props:
                existing[props["title"]] = props["sheetId"]
    return existing


def clear_and_write(service, sheet_name: str, rows: list[list]):
    """Clear a sheet then write rows starting at A1."""
    service.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID, range=f"'{sheet_name}'"
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{sheet_name}'!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()


def freeze_and_bold_header(service, sheet_id: int, num_cols: int):
    """Freeze row 1 and bold it."""
    service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={
            "requests": [
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sheet_id,
                            "gridProperties": {"frozenRowCount": 1},
                        },
                        "fields": "gridProperties.frozenRowCount",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": {"bold": True},
                                "backgroundColor": {"red": 0.18, "green": 0.37, "blue": 0.64},
                            }
                        },
                        "fields": "userEnteredFormat(textFormat,backgroundColor)",
                    }
                },
            ]
        },
    ).execute()


# ---------------------------------------------------------------------------
# Sheet data definitions
# ---------------------------------------------------------------------------

SITE_META_ROWS = [
    ["key", "value", "notes"],
    ["nav_brand", "DEMO • Kendall-Bar • Biological & Physical Oceanography", "Top-left nav bar text"],
    ["nav_tab_syllabus", "Syllabus", "First nav tab label"],
    ["nav_tab_lecture", "Week 13", "Second nav tab label"],
    ["hero_tag", "DEMO COURSE WEBSITE", "Small label above h1 on syllabus page"],
    ["hero_h1", "Biological & Physical Oceanography", "Main title on syllabus page"],
    ["hero_subtitle", "Advanced topics from phytoplankton to fisheries, with emphasis on physical processes and their ecological implications.", ""],
    ["course_schedule_heading", "Course Schedule", "Section heading above week list"],
    ["section_tab_overview", "Overview", ""],
    ["section_tab_0", "Intro · Climate Change", ""],
    ["section_tab_1", "II · Biodiversity Monitoring", ""],
    ["section_tab_2", "III · Carbon Sequestration", ""],
    ["section_tab_3", "IV–V · Experiments & Adaptation", ""],
    ["overview_connecting_thread", "Long-term monitoring (CalCOFI, Argo, IFCB, MARINe) gives us the baseline. Physical oceanography gives us the mechanism. Biology gives us both the problem and potential solutions. Data visualization is what makes all of this accessible to decision-makers.", "Key concept box at bottom of overview"],
]

LECTURE_HERO_ROWS = [
    ["key", "value", "notes"],
    ["week_label", "Week 13 · Lecture", "Small label above h1"],
    ["h1", "Science to Solutions: Data Visualization for Understanding the Power of Biology for Climate Solutions", "Main lecture title"],
    ["subtitle", "From physics to biology — how ocean dynamics shape life, and how biodiversity can protect us from a changing climate.", ""],
    ["meta_duration", "⏱ 50 minutes", ""],
    ["meta_reading", "📖 Ch. 9–12", ""],
    ["meta_activities", "🧪 4 active learning moments", ""],
    ["meta_tools", "🌊 Live data · Real tools", ""],
    ["overview_h2", "What this lecture is about", ""],
    ["overview_intro", "By Week 13 you've mastered the physics and biology of the ocean. Today we ask: so what? Three interconnected case studies show where oceanographic science becomes actionable — through monitoring, mitigation, and adaptation. The throughline is data visualization as the bridge between science and policy.", ""],
]

SUMMARY_TABLE_ROWS = [
    ["part", "topic", "physical_driver_summary", "physical_driver_bullets", "biological_impact_summary", "biological_impact_bullets", "human_element_summary", "human_element_bullets", "opportunities_summary", "opportunities_bullets", "challenges_summary", "challenges_bullets", "video_links_json", "notes"],

    # Intro
    ["Intro — Temperature Change Over Time",
     "Ocean heat & storm intensification",
     "Ocean stores heat that fuels rapid hurricane intensification.",
     ">90% of excess greenhouse heat absorbed since 1970\nSubsurface warm water = storm fuel before landfall",
     "Warming both intensifies storms and destroys reef storm barriers.",
     "Bleached reefs lose wave-breaking capacity\nCoral loss compounds flood risk during storms",
     "Harvey, Ida, and Otis all rapidly intensified over warm water.",
     "Forecast models caught off guard each time\nEmergency managers had insufficient warning",
     "Argo floats now feed ocean heat into hurricane models.",
     "3D heat content in near real-time\nOperational intensity forecasting improved",
     "Reefs degrade fastest when storms are strongest.",
     "Flattened reef structure = no wave attenuation\nProtection lost precisely when most needed",
     "",
     ""],

    ["Intro — Temperature Change Over Time",
     "ENSO — El Niño / La Niña",
     "Trade wind weakening lets warm water slosh east, suppressing upwelling.",
     "El Niño: winds weaken → warm water moves east\nLa Niña: strong winds → cool, productive eastern Pacific",
     "El Niño shifts plankton communities and weakens carbon export.",
     "Diatoms → small flagellates under El Niño\nLa Niña restores anchovy-regime productivity",
     "Global sectors depend on ENSO forecasts with limited skill.",
     "Fisheries, agriculture, disaster management affected\nUseful forecast window: only 6–9 months ahead",
     "OceanBench benchmarks ML models for longer ENSO forecasts.",
     "Pushes toward more reliable multi-season forecasts\nOpen benchmark enables rapid model comparison",
     "A warmer baseline makes El Niño harder to predict.",
     "Models trained on cooler past become less reliable\nEach event starts from a higher heat state",
     json.dumps([
         {"label": "▶ What is El Niño", "url": "https://www.youtube.com/watch?v=WPA-KpldDVc"},
         {"label": "▶ History", "url": "https://www.youtube.com/watch?v=xcg8CKv1XL4"},
         {"label": "▶ Temperature anomalies", "url": "https://www.youtube.com/watch?v=gaFjlZxM7S4"},
     ]),
     ""],

    # Part I
    ["Part I — Anthropogenic and Natural Drivers of Climate Variability",
     "Pacific Decadal Oscillation (PDO)",
     "A 20–30 year North Pacific temperature swing modulates ENSO.",
     "Sets the background state for each ENSO cycle\nWarm/cool phases shift upwelling intensity",
     "PDO phase determines whether sardines or anchovies dominate.",
     "Warm PDO → sardines; cool PDO → anchovies\nConfirmed by 1,700-year fish-scale sediment record",
     "Catch limits set without PDO context chronically misfire.",
     "Over-fishing during cool phase; under-fishing during warm\nPolicy needs decadal context, not just annual data",
     "Sediment cores extend PDO records far beyond instruments.",
     "Santa Barbara Basin cores span 1,700 years\nFish scales preserve species-level regime signal",
     "Only ~3 full PDO cycles exist in the modern record.",
     "Statistically inadequate without paleo data\nEach cycle takes 20–30 years to complete",
     "", ""],

    ["Part I — Anthropogenic and Natural Drivers of Climate Variability",
     "Sardine collapse & CalCOFI",
     "PDO warm phase elevated sardine habitat via California Current upwelling.",
     "Natural productivity cycle, not just fishing pressure\nWarm phase made high catches temporarily sustainable",
     "Overfishing compounded a natural population crash, not caused it.",
     "Sardine/anchovy alternation documented for 1,700+ years\nCollapse would have happened; fishing accelerated it",
     "Peak catch of 791,334 tons in 1936–37 ignored warnings.",
     "Cannery Row economic collapse followed\nDisaster prompted CalCOFI founding in 1949",
     "CalCOFI is one of the world's longest continuous ocean datasets.",
     "75+ years of quarterly California Current cruises\nFoundation for all modern ecosystem modeling",
     "One funding gap breaks multi-decadal signal detection for decades.",
     "30 years of context lost per gap\nPolitically vulnerable, scientifically irreplaceable",
     "", ""],

    # Part II
    ["Part II — Biodiversity Monitoring",
     "IOOS / IFCB infrastructure",
     "Integrated sensor network creates a real-time California Current picture.",
     "Buoys, gliders, HF radar, Argo floats, tide gauges\nContinuous, multi-variable, publicly accessible",
     "Species-level plankton ID enables real-time pump efficiency tracking.",
     "First continuous biological monitoring at this resolution\nLinks physics to biology automatically",
     "HAB alerts, shellfish closures, and fisheries rely on this data.",
     "Public infrastructure accessible to anyone\nFeeds regulatory and emergency decisions",
     "Open data enables citizen science and rapid ML development.",
     "Anyone with internet can build classifiers\nStudent and researcher access with no barriers",
     "Sustained funding required; politically exposed despite scientific value.",
     "Federal and state budget cycles threaten continuity\nNetwork loss is irreversible, not just delayed",
     "", ""],

    ["Part II — Biodiversity Monitoring",
     "Harmful algal blooms & Pseudo-nitzschia",
     "El Niño stratification then nutrient injection triggers explosive blooms.",
     "High silicate:nitrogen ratio → domoic acid production\nWarm stratification sets the stage; upwelling pulls trigger",
     "Domoic acid bioaccumulates up the food web to dangerous levels.",
     "Krill → anchovies → sea lions: seizures, strandings\nFilter feeders (shellfish) concentrate toxin",
     "Dungeness crab seasons regularly delayed or closed by blooms.",
     "CDPH monitors shellfish toxicity coast-wide\nEconomic losses to fishing industry each severe year",
     "IFCB cell spikes can trigger toxin testing before danger.",
     "Early warning window before shellfish become unsafe\nAllows pre-emptive rather than reactive closures",
     "A bloom ≠ a toxin event; both must be tracked separately.",
     "Cell counts alone don't predict domoic acid levels\nParallel chemical monitoring required for true early warning",
     "", ""],

    # Part III
    ["Part III — Carbon Sequestration",
     "Biological carbon pump",
     "Upwelling fuels phytoplankton; sinking below 1,000 m sequesters carbon.",
     "Surface CO₂ fixed → particles sink → deep storage\nCarbon removed from atmosphere for centuries+",
     "Cell size and type determine how much carbon actually escapes.",
     "Diatoms + large zooplankton → fast-sinking export\nSmall flagellates → carbon recycled near surface",
     "Ocean absorbs ~25% of annual anthropogenic CO₂.",
     "Pump efficiency directly sets warming per unit emission\nSmall changes in efficiency have large climate consequences",
     "IFCB tracks pump efficiency via community composition in real time.",
     "Species ratios proxy export potential continuously\nNo sediment trap needed for first-order monitoring",
     "Warming degrades the pump through four simultaneous pathways.",
     "Stronger stratification → less nutrient supply\nFaster bacterial breakdown, smaller cells, less ballast",
     json.dumps([
         {"label": "▶ Carbon sequestration in the ocean (Exploratorium)", "url": "https://www.youtube.com/watch?v=KvHSb8X5F_o"},
         {"label": "▶ Carbon export animation", "url": "https://www.youtube.com/watch?v=CHCa3bcvk14"},
     ]),
     ""],

    ["Part III — Carbon Sequestration",
     "Ocean iron fertilization / mCDR",
     "Iron limits ~30% of the ocean; adding it triggers deep-export blooms.",
     "HNLC regions have nutrients but no iron\nFe addition → diatom bloom → potential export",
     "Blooms confirmed; whether carbon reaches depth is unresolved.",
     "Field experiments show surface response clearly\nDepth remineralization vs. true sequestration still debated",
     "ExOIS builds MRV frameworks before scaling any intervention.",
     "Supplement to — not substitute for — emissions cuts\nGovernance and attribution frameworks being developed",
     "California Current network is an ideal instrumented field trial baseline.",
     "75+ years of background data for signal detection\nMulti-sensor coverage allows rigorous evaluation",
     "Measuring \"carbon that didn't return\" is a fundamental attribution problem.",
     "Dynamic ocean makes counterfactual hard to define\nNo easy solution yet exists",
     "", ""],

    # Part IV
    ["Part IV — Natural Experiments",
     "Wildfire ash & coastal ocean",
     "Ash delivers iron and nitrogen but also potentially toxic compounds.",
     "Perturbs an already El Niño-stressed community\nMixed signal: fertilizer + toxin simultaneously",
     "Three possible outcomes are being tested simultaneously.",
     "Fertilization bloom, productivity suppression, or toxic shift\nResults not yet published as of early 2025",
     "CalCOFI detected ash in SCB; managers must act before science resolves.",
     "Ash particles found in samples from Jan–Mar 2025\nAdvisories issued under scientific uncertainty",
     "Existing CalCOFI + IFCB baseline makes ash signal detectable.",
     "Without long-term baseline, anomaly would be invisible\nNatural experiment only works with prior monitoring",
     "LA fires hit an ocean already weakened by 18 months of El Niño.",
     "Compound stressors make attribution harder\nBaseline community already disrupted before ash arrived",
     "", ""],

    ["Part IV — Natural Experiments",
     "2023–24 ocean-memory El Niño",
     "Deep Pacific heat from three La Niñas spread east via subsurface waves.",
     "El Niño formed without the usual atmospheric wind signal\nHeat transported oceanically, not wind-driven",
     "Abrupt warm intrusion disrupted anchovy regime mid-cycle.",
     "Phytoplankton community shifted rapidly\nCarbon export weakened without a full seasonal transition",
     "Wind-calibrated forecast models badly underforecast this event.",
     "Atmospheric indices appeared weak → managers underprepared\nMedia and policy response lagged the real ocean signal",
     "OceanBench ML models trained on Argo subsurface data detect this.",
     "Subsurface heat state more informative than surface indices\nBetter suited to ocean-memory event detection",
     "More La Niña heat loading makes ocean-memory events more frequent.",
     "Each La Niña cycle adds to deep Pacific heat reservoir\nEvents will be harder to forecast as baseline shifts",
     json.dumps([
         {"label": "OceanBench (NeurIPS 2025)", "url": "https://neurips.cc/virtual/2025/loc/san-diego/poster/121394"},
     ]),
     ""],

    # Part V
    ["Part V — Climate Mitigation and Adaptation",
     "Reefs & mangroves: NBS-Adapts",
     "Reef crests, mangroves, and marshes dissipate waves at no maintenance cost.",
     "Reefs: ~97% of wave energy dissipated\nMangroves reduce surge; marshes attenuate per meter",
     "Biodiverse reefs resist bleaching and maintain wave-breaking structure.",
     "Higher diversity → better thermal stress tolerance\nStructural complexity is what breaks waves",
     "NBS-Adapts translates ecology into flood risk language for planners.",
     "Outputs: flood depth, protected property value\nSpeaks to FEMA, insurers, and city planners",
     "NBS delivers wave attenuation, carbon storage, and fisheries together.",
     "Lower cost than hard infrastructure\nMultiple co-benefits from a single ecosystem",
     "Warming bleaches reefs; rising seas drown marshes faster than growth.",
     "Coastal defenses degrade as storm risk increases\nProtection and threat move in opposite directions",
     "", ""],

    ["Part V — Climate Mitigation and Adaptation",
     "Sea level rise & the intertidal: ShoreCast",
     "Circulation models map larval pathways and thermal refugia under SLR.",
     "Downscaled climate projections identify cool-water refugia\nROMS-based connectivity from Edwards Lab",
     "30+ years of MARINe surveys show species persistence under SLR scenarios.",
     "Connectivity modeling reveals which sites seed others\nLong-term data makes scenario projections credible",
     "ShoreCast gives MPA placement a scientific rather than political basis.",
     "Prioritizes source populations and refugia\nEvidence base replaces negotiation for siting decisions",
     "Three decades of MARINe data make SLR scenario modeling actionable.",
     "Managers can act on projections today\nLong time series is the irreplaceable foundation",
     "Connectivity data not yet integrated into MPA policy.",
     "Gaps in network where science says protection matters most\nScience-policy translation lag leaves refugia unprotected",
     "", ""],
]

SECTION_HEADERS_ROWS = [
    ["section_id", "h2", "h2_subtitle", "intro_paragraph", "slide_box_label", "notes"],
    ["section0",
     "Intro · Temperature Change Over Time",
     "Part I · Anthropogenic and Natural Drivers of Climate Variability",
     "Before we can understand what biology can do for us, we need to understand the scale of the problem. Surface temperatures have been rising globally for over a century — and the data that tells us this story comes from an extraordinary distributed network of sensors on land and ocean. This section grounds today's lecture in the physical reality of a warming planet, then examines the natural oscillations (ENSO, PDO) that ride on top of that warming signal.",
     "Lecture overview · Intro & Part I",
     ""],
    ["section1",
     "Part II · Biodiversity Monitoring",
     "",
     "Long-term programs like CalCOFI transform isolated measurements into ecological understanding. The California Current is a living laboratory for how ENSO cascades into biological community structure — and real-time tools like the IFCB let us see those dynamics right now.",
     "Lecture overview · Part II",
     ""],
    ["section2",
     "Part III · Carbon Sequestration",
     "",
     "We know phytoplankton fix carbon. But how much actually reaches the deep ocean, how is that controlled, and how might it change as the climate warms? This section connects the biological pump to climate mitigation and the emerging field of marine CDR.",
     "Lecture overview · Part III",
     ""],
    ["section3",
     "Part IV · Natural Experiments",
     "Part V · Climate Mitigation and Adaptation",
     "More ocean heat means more intense hurricanes and faster sea level rise. Coastal communities face escalating flood risk — but healthy ecosystems are a first line of defense. This is where biodiversity science meets infrastructure planning, property insurance, and billions in public investment.",
     "Lecture overview · Parts IV & V",
     ""],
]

# card_id is used as foreign key in resources sheet
CARDS_ROWS = [
    ["card_id", "section_id", "card_type", "h3", "badge", "body_text", "key_concept", "activity_label", "activity_prompt", "activity_feedback", "notes"],

    # --- section0 cards ---
    ["s0_nasa_globe", "section0", "viz_card",
     "Where do global temperature measurements come from?", "NASA SVS · Interactive 3D",
     "NASA Scientific Visualization Studio. This is an interactive 3D model! Click and drag to rotate the model. This map displays changing surface temperature anomalies from 1880 to 2024. It does not show absolute temperatures; instead, it shows how much warmer or cooler each region of Earth was compared to the average from 1951 to 1980. Average temperatures are shown in white, with higher-than-normal temperatures shown in red and lower-than-normal temperatures shown in blue. Earth's global surface temperatures in 2024 were the warmest on record: 1.28 degrees Celsius (2.30 degrees Fahrenheit) above the agency's 20th-century baseline (1951–1980).\n\nScientific consulting by: Gavin A. Schmidt\nProduced by: Kathleen Gaeta\nVisualizations by: Mark SubbaRao",
     "", "", "", ""],

    ["s0_measurement_network", "section0", "viz_card",
     "The measurement network behind global temperature records", "GHCN · ICOADS · GISS",
     "The 2023 GISS Surface Temperature Analysis (GISTEMPv4) integrates two independent measurement streams. Understanding where the data comes from is the first step in trusting — and critiquing — the global temperature record.\n\n🌍 Land: GHCN — The Global Historical Climatology Network integrates records from ~27,000 weather stations worldwide, some dating back to the mid-1800s. NOAA quality-controls and homogenizes the records to correct for station moves, instrument changes, and urban heat island effects.\n\n🌊 Ocean: ICOADS — The International Comprehensive Ocean-Atmosphere Data Set compiles sea surface temperature measurements from ship engine intake logs, hull sensors, drifting buoys, Argo floats, and moored buoys. Coverage has improved dramatically since the 1950s with the expansion of volunteer observing ships and autonomous platforms.\n\nStat: +1.2°C — Global mean surface temperature anomaly above pre-industrial baseline (1850–1900) as of 2023\nStat: 2023 — Hottest year on record — approximately +1.45°C above the pre-industrial baseline; 10 consecutive months of record monthly temperatures\nStat: >90% — Fraction of that excess heat absorbed by the ocean — making ocean heat content the most comprehensive measure of planetary energy imbalance",
     "Why does this matter for today's lecture? Every system we'll examine — CalCOFI's biological time series, the biological carbon pump, coastal flood risk from hurricanes — is being driven or modulated by this underlying warming signal. The temperature record is not just background context; it is the forcing function for everything else.",
     "", "", ""],

    ["s0_explore_record", "section0", "viz_card",
     "Explore the full temperature record", "NASA GISS · Public data",
     "", "", "", "", ""],

    # --- section1 cards ---
    ["s1_enso_toggle", "section1", "viz_card",
     "ENSO state & California Current biology", "Interactive",
     "Toggle between climate states to see how ENSO drives conditions in the California Current.\n\nButton 1: 🔵 La Niña / Neutral\nButton 2: 🔴 El Niño 2015–16\nButton 3: 🟢 Today (Spring 2026)",
     "", "", "", ""],

    ["s1_enso_comparison", "section1", "viz_card",
     "El Niño vs. La Niña: what IFCB shows", "Community comparison",
     "La Niña / cool upwelling:\n✓ Strong upwelling · nutrient-rich\n✓ Diatom blooms (Pseudo-nitzschia, Chaetoceros)\n✓ High total cell abundance\n✓ Anchovy, sardine, krill thrive\n\nEl Niño / warm stratified:\n✗ Deep thermocline blocks upwelling\n✗ Dinoflagellates, small flagellates\n✗ Lower total abundance\n✗ Seabird die-offs, sea lion strandings",
     "", "", "", ""],

    ["s1_dashboard_preview", "section1", "viz_card",
     "CalCOFI & IFCB dashboard preview", "Data Integration",
     "This section is wired to load a JSON payload from data/calcofi_ifcb_sample.json. Replace that file with your own CalCOFI / IFCB JSON to explore real monitoring data inside the lecture flow.\n\nMetric labels: Latest CalCOFI chlorophyll | Latest CalCOFI nitrate | Latest IFCB total cells\nNested chart title: CalCOFI trend chart\nSchema note: Use 'calcofi' and 'ifcb' keys in JSON to map time series, taxa counts, and sensor metadata.",
     "", "", "", ""],

    ["s1_hypothesis_activity", "section1", "activity_card",
     "Active Learning Activity", "4 min · individual → pair",
     "",
     "",
     "Hypothesis prompt",
     "Write a 1–2 sentence testable hypothesis: How would you expect phytoplankton abundance and community composition (IFCB) to differ today vs. the same date during the 2015–16 El Niño?",
     "Good hypotheses invoke the physical mechanism: weakened trade winds → warm water → deep thermocline → reduced Ekman upwelling → less nutrient supply → less phytoplankton growth. In April 2016, SST anomalies off California were +2–3°C; thermocline depth ~80–100m vs ~40m in neutral years. IFCB data from that period shows dramatically lower diatom abundances and community shift toward smaller warm-water taxa. Spring 2026 is near-neutral, so we expect higher diatom abundances and stronger upwelling signal."],

    ["s1_wildfire", "section1", "viz_card",
     "Frontier science: LA Wildfire ash & the coastal ocean", "Ongoing · 2025",
     "CalCOFI water samples from January–March 2025 detected ash-derived particles from the Palisades and Eaton wildfires in the Southern California Bight — an unplanned natural experiment in real time.\n\nOpen scientific question: What happens when wildfire ash falls on the ocean?\nWildfire ash contains iron, nitrogen, phosphorus, and potentially toxic compounds. Based on iron limitation theory, we might predict a fertilization effect. But the outcome depends on ash chemistry, background nutrients, and what organisms are present. It could also suppress communities via toxins or light limitation.\nStatus: ⚡ Data collection ongoing — results not yet published",
     "",
     "Discussion question (pairs · 2 min)",
     "Given what you know about iron limitation and the biological pump — what would you predict happens when a large ash plume settles on the surface ocean? Would you expect a bloom? Would carbon export increase? What could go wrong?",
     ""],

    # --- section2 cards ---
    ["s2_bio_pump", "section2", "viz_card",
     "The biological carbon pump", "Concept review · Ch. 10",
     "🌞 Euphotic zone (0–200 m): Phytoplankton fix CO₂ + H₂O via photosynthesis → organic carbon. Death, grazing → particles. CO₂ + H₂O ⇌ H₂CO₃ ⇌ HCO₃⁻ + H⁺ equilibrium governs surface chemistry.\n\n🌑 Mesopelagic / twilight zone (200–1000 m): Bacterial respiration remineralizes most particles here. Only ~10–20% of surface production exits this zone. Fecal pellets and mucous feeding webs escape remineralization.\n\n🌊 Deep ocean (>1000 m): Carbon sequestered here is removed from the atmosphere for centuries to millennia. Carbonate dissolution adds HCO₃⁻ to deep-sea alkalinity.",
     "", "", "", ""],

    ["s2_leaky_pump", "section2", "viz_card",
     "A warming ocean is a leakier pump", "Mechanism",
     "Stronger stratification: Warmer SSTs deepen thermocline, reducing nutrient supply via Ekman upwelling.\n\nFaster remineralization: Bacterial metabolism scales with temperature (Q₁₀ ≈ 2). Warmer water → more carbon respired in the mesopelagic.\n\nCommunity shifts: Small cells dominate warm, stratified conditions — lower sinking rates, routed through the microbial loop.\n\nAcidification: Lower pH reduces calcification — coccolithophore and pteropod shells act as ballast. Less ballast → shallower remineralization.",
     "", "", "", ""],

    ["s2_mcdr", "section2", "viz_card",
     "Marine Carbon Dioxide Removal", "Frontier science",
     "Ocean iron fertilization: Add Fe to HNLC regions → bloom → export. Does carbon actually reach depth? ExOIS develops rigorous MRV frameworks.\n\nAlkalinity enhancement: Add alkaline minerals → shift carbonate equilibrium → ocean absorbs more atmospheric CO₂. Ecotoxicology uncertain.\n\nMacroalgae CDR: Grow kelp at scale → sink biomass. Logistically challenging; permanence of sequestration debated.\n\n⚠ Emissions first: All mCDR approaches are supplements, not substitutes. Unmitigated emissions would require CDR at implausible scales.",
     "", "", "", ""],

    # --- section3 cards ---
    ["s3_ocean_heat", "section3", "viz_card",
     "Ocean heat content & storm intensification", "Video + context",
     "Rising ocean heat content: Ocean absorbed >90% of excess heat since 1970. Upper 2000m warming is accelerating. Provides fuel for tropical cyclone intensification.\n\nRapid intensification: Hurricanes crossing warm core eddies can intensify 2+ categories in <24 hours. Harvey, Ida, Otis all showed rapid intensification over anomalously warm water.",
     "Sea level rise + more intense storms = catastrophic compound flooding risk. Federal flood insurance, municipal infrastructure, and property markets are all exposed. This creates massive policy demand for coastal science.",
     "", "", ""],

    ["s3_nbs_ecosystems", "section3", "viz_card",
     "Biology as coastal infrastructure", "Nature-based solutions",
     "🪸 Coral reefs: Attenuate ~70% of wave energy. Surge buffer for tropical coasts. Vulnerable to bleaching above +1°C anomaly.\n\n🌿 Mangroves: Reduce storm surge, trap sediment, stabilize shorelines. Global extent declined ~50% since 1950s.\n\n🌾 Salt marshes: Attenuate wave energy per meter of width, reduce erosion. Threatened by drowning as SLR outpaces accretion.\n\n🦪 Oyster reefs: Wave attenuation in estuaries, reduce erosion. Can grow vertically to keep pace with moderate SLR.\n\nThe paradox: Climate change threatens the ecosystems that protect us from climate change. More resilient, biodiverse ecosystems perform better under stress — biodiversity is physically protective infrastructure.",
     "", "", "", ""],

    ["s3_decision_tools", "section3", "viz_card",
     "Data visualization tools for decision-making", "Interactive tools · UCSC",
     "",
     "",
     "Exit ticket · think-pair · 0:45",
     "For any one tool or dataset we explored today — CalCOFI/IFCB, ExOIS, NBS-Adapts, or ShoreCast — who is the non-scientist audience that most needs this information? What would you change to make it more useful for them?",
     "Three takeaways:\n1. Long-term monitoring is foundational — without decades of data, we can't separate signal from noise in a changing ocean.\n2. The biological pump is climate-sensitive, and mCDR interventions offer pathways — but only if we can rigorously measure whether they work.\n3. Biodiversity is infrastructure. Healthier, more diverse ecosystems are more resilient and more physically protective."],
]

# resource_type: tool_card | youtube_card | video_link | youtube_inline
RESOURCES_ROWS = [
    ["resource_id", "card_id", "resource_type", "title", "type_badge", "description", "link_text", "url", "thumbnail_alt", "video_label", "notes"],

    # s0_explore_record tools
    ["r_gistemp", "s0_explore_record", "tool_card",
     "NASA GISS Surface Temperature Analysis (GISTEMPv4)", "NASA data",
     "Interactive global temperature anomaly maps and time series from 1880 to present. Downloadable datasets, visualizations, and the full methodology documentation for GISTEMPv4.",
     "Open GISTEMP", "https://data.giss.nasa.gov/gistemp/", "", "", ""],

    ["r_nasa_svs", "s0_explore_record", "tool_card",
     "NASA Scientific Visualization Studio — GISS Measurement Locations", "NASA SVS",
     "Full resolution video and still downloads of the measurement location visualization shown above, optimized for Science On a Sphere spherical displays. Includes equirectangular and flat projection formats.",
     "Open NASA SVS page", "https://svs.gsfc.nasa.gov/5208/", "", "", ""],

    # s1_enso_comparison tools
    ["r_ifcb_dashboard", "s1_enso_comparison", "tool_card",
     "IFCB Dashboard — Scripps Pier", "Live data",
     "Real-time imaging flow cytometry from La Jolla, CA. Automated species-level phytoplankton classification and multi-year time series.",
     "Open IFCB dashboard", "https://ifcb-data.whoi.edu/timeline?dataset=IFCB104", "", "", ""],

    ["r_calcofi_portal", "s1_enso_comparison", "tool_card",
     "CalCOFI Data Portal", "Time series",
     "75+ years of quarterly cruises sampling the California Current Ecosystem — chlorophyll, zooplankton, fish larvae, nutrients, T/S profiles. One of the world's longest continuous marine datasets.",
     "Explore CalCOFI data", "https://calcofi.org/data", "", "", ""],

    # s2_bio_pump youtube cards
    ["r_carbon_seq_video", "s2_bio_pump", "youtube_card",
     "Carbon sequestration in the ocean — Exploratorium presentation", "",
     "Watch for where carbon goes after a phytoplankton cell dies",
     "", "https://www.youtube.com/watch?v=KvHSb8X5F_o",
     "Carbon sequestration animation", "Video · ~3 min · opens on YouTube", ""],

    ["r_carbon_export_video", "s2_bio_pump", "youtube_card",
     "Carbon export animation — biological pump process", "",
     "Alternative framing of the same carbon export pathway",
     "", "https://www.youtube.com/watch?v=CHCa3bcvk14",
     "Carbon export animation", "Video · alternate version · opens on YouTube", ""],

    # s2_mcdr tool
    ["r_exois", "s2_mcdr", "tool_card",
     "ExOIS — Exploring Ocean Iron Solutions", "Research initiative",
     "Collaborative initiative developing methodologies for evaluating the efficacy, safety, and permanence of ocean iron-based CDR. Central challenge: measuring what didn't happen (un-emitted CO₂) in a dynamic, variable ocean.",
     "Visit exois.org", "https://www.exois.org", "", "", ""],

    # s3_ocean_heat inline video
    ["r_argo_video", "s3_ocean_heat", "youtube_inline",
     "Argo float animation — 3D ocean heat content", "",
     "Produced for Scripps. Shows ocean heat content — not just sea surface temperature.",
     "", "https://www.youtube.com/watch?v=Pc4KWFKVj_Q",
     "Argo float animation", "Video · Scripps Institution of Oceanography", ""],

    # s3_decision_tools tool cards
    ["r_nbs_adapts", "s3_decision_tools", "tool_card",
     "NBS Adaptation Explorer", "Flood risk tool",
     "Quantifies current and future storm-driven flood risk and values how coral reefs and mangroves reduce that risk. Shows flood depth and extent with vs. without reef protection, with dollar-valued ecosystem services for FEMA, insurers, and coastal planners. Developed at UC Santa Cruz.",
     "Open NBS Explorer", "https://nbs-adapts.coastalresilience.ucsc.edu/", "", "", ""],

    ["r_shorecast", "s3_decision_tools", "tool_card",
     "ShoreCast — Intertidal Conservation Planning", "Decision support",
     "Decision support system for California's rocky intertidal. Built on MARINe long-term monitoring + USGS LiDAR elevation + ROMS-based larval connectivity from the Edwards Lab. Shows species distributions under SLR scenarios, biodiversity metrics, and larval source-sink mapping. Developed by the Raimondi lab at UCSC.",
     "Open ShoreCast", "https://intertidal-sea-level-rise.pbsci.ucsc.edu/", "", "", ""],
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Populate bio-oce Google Sheet")
    parser.add_argument("--credentials", required=True,
                        help="Path to OAuth 2.0 Desktop client credentials JSON")
    args = parser.parse_args()

    if not os.path.exists(args.credentials):
        print(f"ERROR: credentials file not found: {args.credentials}", file=sys.stderr)
        sys.exit(1)

    print("Authenticating…")
    creds = get_credentials(args.credentials)
    service = build("sheets", "v4", credentials=creds)

    sheet_names = ["site_meta", "lecture_hero", "summary_table",
                   "section_headers", "cards", "resources"]

    print("Ensuring sheets exist…")
    sheet_ids = ensure_sheets(service, sheet_names)

    datasets = {
        "site_meta":       SITE_META_ROWS,
        "lecture_hero":    LECTURE_HERO_ROWS,
        "summary_table":   SUMMARY_TABLE_ROWS,
        "section_headers": SECTION_HEADERS_ROWS,
        "cards":           CARDS_ROWS,
        "resources":       RESOURCES_ROWS,
    }

    for name, rows in datasets.items():
        print(f"Writing {name} ({len(rows)-1} data rows)…")
        clear_and_write(service, name, rows)
        freeze_and_bold_header(service, sheet_ids[name], len(rows[0]))

    print("\nDone! Open your spreadsheet at:")
    print(f"  https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")


if __name__ == "__main__":
    main()
