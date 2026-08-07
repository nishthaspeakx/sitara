#!/usr/bin/env python3
"""Build the premium interactive HTML Phase-1 v2 spec for Sitara."""
import re, subprocess, html, pathlib

BASE = pathlib.Path("/home/claude/phase1v2")
SPEC = BASE / "spec2.md"
DIAG = BASE / "diagrams"
OUT  = BASE / "Sitara_Phase1_Specification_v2.html"

frag = subprocess.run(
    ["pandoc", str(SPEC), "-f", "markdown-yaml_metadata_block", "-t", "html", "--wrap=none"],
    capture_output=True, text=True, check=True).stdout

parts = re.split(r'(?=<h1)', frag)
sections = parts[1:]

# section number -> list of (svg, title, caption)
DIAGRAMS = {
    2:  [("02_multilingual_experience.svg", "The Multilingual Experience",
          "One language choice governs everything — and no silent English fallback, ever.")],
    3:  [("03_voice_system.svg", "Tara's Regional Voice System",
          "Per-language provider routing: anchor clone for EN/Hinglish/HI, Azure Custom Neural Voice for the five regional languages, universal failover.")],
    5:  [("06_astrology_validation.svg", "Astrology Calculation & Validation — the five layers",
          "Internal Swiss Ephemeris engine, external APIs, golden set, nightly comparison, cite-or-die interpretation.")],
    6:  [("09_system_architecture.svg", "System Architecture — Next.js · Python · MongoDB",
          "Three Python services, one Next.js PWA, MongoDB Atlas with Vector Search, adapters around every provider."),
         ("10_mongodb_dataflow.svg", "MongoDB Data Flow",
          "28 collections: identity, astrology caches, the daily loop, conversation & memory, money, ops.")],
    7:  [("05_morning_pipeline.svg", "Morning-Brief Generation Pipeline",
          "Timezone-aware waves, shared panchang cache, priority queues, idempotency, honest degradation."),
         ("11_scaling_architecture.svg", "Scaling Architecture — Stage 1 → 4",
          "1K to 10M users: what changes, what it costs, what triggers each upgrade.")],
    8:  [("12_multiregion_failover.svg", "Multi-Region Failover & DR",
          "ap-south-1 primary, us-east-1 warm standby, PITR backups, provider degradation ladder."),
         ("14_deployment_flow.svg", "Zero-Downtime Deployment Flow",
          "CI gates (including the golden-set astrology gate), canary, burn-rate-watched rollout, automatic rollback.")],
    9:  [("07_conversation_pipeline.svg", "Conversation Pipeline — every turn",
          "The mandatory sequence: detection, safety, facts, validators, voice, avatar, memory."),
         ("08_memory_retrieval.svg", "Memory Retrieval",
          "Consent chips in, Vector Search out — visibility-gated, user-controlled, hard-deletable.")],
    10: [("01_user_journey.svg", "End-to-End User Journey",
          "Discovery to daily loop — in the user's language at every step.")],
    14: [("13_safety_escalation.svg", "Safety Escalation L1–L5",
          "Astrology framing is removed the moment risk appears; native reviewers own the per-language fear-phrasing corpus.")],
    15: [("15_roadmap.svg", "22-Week Roadmap + Language Waves",
          "Option A: three complete languages at launch (mid-Jan 2027), waves complete all eight by May 2027.")],
    28: [("16_route_map.svg", "Canonical Route Map & Navigation Rules",
          "Four tabs, onboarding stack, overlays, deep links, safety takeover — every route, one screen entry each.")],
}

def diagram_blocks(secno):
    out = []
    for fn, title, caption in DIAGRAMS.get(secno, []):
        svg = (DIAG / fn).read_text()
        svg = re.sub(r'<\?xml[^>]*\?>', '', svg)
        out.append(f'<figure class="diagram"><figcaption><span class="dg-kicker">Diagram</span>'
                   f'<span class="dg-title">{html.escape(title)}</span>'
                   f'<span class="dg-cap">{html.escape(caption)}</span></figcaption>'
                   f'<div class="dg-body">{svg}</div></figure>')
    return "".join(out)

nav_items = []
body_sections = []

for i, s in enumerate(sections):
    m = re.match(r'<h1[^>]*>(.*?)</h1>', s, re.S)
    heading = html.unescape(re.sub(r'<[^>]+>', '', m.group(1))) if m else f"Section {i}"
    if i == 0:
        continue
    num_m = re.match(r'\s*(\d+)\.', heading)
    secno = int(num_m.group(1)) if num_m else i
    short = re.sub(r'^\s*\d+\.\s*', '', heading)
    nav_label = re.split(r'\s+[—(]', short)[0].strip().rstrip('—-· ')
    nav_items.append((secno, nav_label))
    inner = re.sub(r'^<h1', '<h1 class="sec-h"', s, count=1)
    dg = diagram_blocks(secno)
    if dg:
        inner = re.sub(r'(</h1>)', r'\1' + dg.replace('\\', '\\\\'), inner, count=1)
    body_sections.append(f'<section class="spec-sec" id="sec{secno}">{inner}</section>')

nav_html = "\n".join(
    f'<a class="nav-item" href="#sec{n}"><span class="nav-num">{n:02d}</span><span class="nav-lab">{html.escape(lab)}</span></a>'
    for n, lab in nav_items)

CHIPS = [
    ("Stack", "Next.js 15 · Python FastAPI · MongoDB Atlas"),
    ("Localisation", "Whole-app native language — no English leakage"),
    ("Launch languages", "EN · Hinglish · HI — waves to all 8 by May '27"),
    ("Voice", "Anchor clone + Azure CNV per language"),
    ("Tara", "Photoreal presence · call-first · daily Stories"),
    ("Astrology", "SwissEph engine + DivineAPI · 5 validation layers"),
    ("Timeline", "22 weeks · launch mid-Jan 2027"),
    ("Budget", "₹2.34Cr canonical baseline · tranche gates W8/W19"),
]
chips_html = "".join(
    f'<div class="chip"><span class="chip-k">{k}</span><span class="chip-v">{v}</span></div>'
    for k, v in CHIPS)

page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sitara · Phase 1 — Specification v2</title>
<style>
:root {{
  --navy:#1E2761; --navy-deep:#151B45; --navy-ink:#0F1330;
  --gold:#C9A227; --gold-soft:#E7D391; --cream:#FAF7F0; --paper:#FFFFFF;
  --ink:#23263A; --muted:#6B6F85; --line:#E4E0D2;
  --serif:Georgia,'Times New Roman',serif;
  --sans:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
}}
* {{ box-sizing:border-box; margin:0; padding:0; }}
html {{ scroll-behavior:smooth; scroll-padding-top:24px; }}
body {{ font-family:var(--sans); color:var(--ink); background:var(--cream); line-height:1.65; }}
.wrap {{ display:flex; min-height:100vh; }}
nav.side {{
  width:300px; flex:0 0 300px; background:var(--navy-ink); color:#CBD0E8;
  position:sticky; top:0; height:100vh; overflow-y:auto; padding:26px 0 40px;
  scrollbar-width:thin; scrollbar-color:#3A4173 transparent;
}}
nav.side::-webkit-scrollbar {{ width:6px; }}
nav.side::-webkit-scrollbar-thumb {{ background:#3A4173; border-radius:3px; }}
.brand {{ padding:0 26px 18px; border-bottom:1px solid rgba(201,162,39,.25); }}
.brand .star {{ color:var(--gold); font-size:22px; letter-spacing:4px; }}
.brand h1 {{ font-family:var(--serif); font-size:26px; color:#fff; letter-spacing:1px; margin-top:4px; }}
.brand p {{ font-size:11.5px; color:#8A90B5; margin-top:6px; text-transform:uppercase; letter-spacing:1.6px; }}
.brand .vtag {{ display:inline-block; margin-top:8px; background:var(--gold); color:var(--navy-ink);
  font-size:10px; font-weight:700; letter-spacing:1px; padding:2px 8px; border-radius:10px; }}
.nav-search {{ margin:16px 20px 6px; }}
.nav-search input {{
  width:100%; padding:8px 12px; border-radius:8px; border:1px solid #3A4173;
  background:#1A2050; color:#E8EAF6; font-size:13px; outline:none;
}}
.nav-search input::placeholder {{ color:#6B72A0; }}
.nav-search input:focus {{ border-color:var(--gold); }}
.nav-list {{ padding:10px 12px; }}
.nav-item {{
  display:flex; gap:10px; align-items:baseline; padding:7px 14px; border-radius:8px;
  color:#C4C9E4; text-decoration:none; font-size:13.2px; transition:background .15s,color .15s;
}}
.nav-item:hover {{ background:rgba(201,162,39,.12); color:#fff; }}
.nav-item.active {{ background:var(--gold); color:var(--navy-ink); font-weight:600; }}
.nav-item.active .nav-num {{ color:var(--navy-ink); }}
.nav-num {{ font-size:10.5px; color:var(--gold); font-weight:700; letter-spacing:.5px; flex:0 0 22px; }}
.nav-item.hidden {{ display:none; }}
main {{ flex:1; min-width:0; }}
header.hero {{
  background:linear-gradient(135deg,var(--navy-ink) 0%,var(--navy) 55%,#2A3578 100%);
  color:#fff; padding:64px 56px 46px; position:relative; overflow:hidden;
}}
header.hero::after {{
  content:"✦"; position:absolute; right:40px; top:28px; font-size:120px;
  color:rgba(201,162,39,.14); line-height:1;
}}
.hero .kicker {{ color:var(--gold); text-transform:uppercase; letter-spacing:3px; font-size:12px; font-weight:600; }}
.hero h2 {{ font-family:var(--serif); font-size:42px; line-height:1.14; margin:14px 0 10px; max-width:860px; }}
.hero .sub {{ color:#B9BFDF; font-size:16.5px; max-width:780px; }}
.hero .promise {{
  margin-top:22px; padding:16px 20px; border-left:3px solid var(--gold);
  background:rgba(255,255,255,.05); font-family:var(--serif); font-style:italic;
  font-size:15.5px; color:#E4E7F7; max-width:780px; border-radius:0 8px 8px 0;
}}
.meta-row {{ margin-top:20px; font-size:12.5px; color:#8A90B5; letter-spacing:.6px; }}
.chips {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:26px 56px 0; transform:translateY(28px); position:relative; z-index:2; }}
.chip {{
  background:var(--paper); border:1px solid var(--line); border-top:3px solid var(--gold);
  border-radius:10px; padding:12px 14px; box-shadow:0 6px 18px rgba(21,27,69,.10);
}}
.chip-k {{ display:block; font-size:10.5px; text-transform:uppercase; letter-spacing:1.4px; color:var(--muted); font-weight:700; }}
.chip-v {{ display:block; font-size:13px; color:var(--navy); font-weight:600; margin-top:3px; line-height:1.35; }}
.content {{ padding:70px 56px 90px; max-width:1100px; }}
.spec-sec {{ background:var(--paper); border:1px solid var(--line); border-radius:14px;
  padding:38px 44px; margin-bottom:30px; box-shadow:0 3px 14px rgba(21,27,69,.05); }}
.spec-sec h1.sec-h {{
  font-family:var(--serif); color:var(--navy); font-size:27px; line-height:1.25;
  padding-bottom:14px; margin-bottom:20px; border-bottom:2px solid var(--gold);
}}
.spec-sec h2 {{ font-family:var(--serif); color:var(--navy); font-size:20px; margin:26px 0 10px; }}
.spec-sec h3 {{ color:var(--navy); font-size:16px; margin:20px 0 8px; }}
.spec-sec p {{ margin:10px 0; font-size:14.8px; }}
.spec-sec ul, .spec-sec ol {{ margin:10px 0 10px 24px; font-size:14.8px; }}
.spec-sec li {{ margin:5px 0; }}
.spec-sec strong {{ color:var(--navy); }}
.spec-sec em {{ color:#4A4E6A; }}
.spec-sec blockquote {{
  border-left:3px solid var(--gold); background:#FCF9F0; padding:12px 18px;
  margin:14px 0; border-radius:0 8px 8px 0; font-size:14.5px;
}}
.spec-sec hr {{ border:none; border-top:1px dashed var(--line); margin:22px 0; }}
.spec-sec code {{ background:#F1EFE6; border:1px solid var(--line); border-radius:4px;
  padding:1px 6px; font-size:13px; color:#5B4A0E; }}
.spec-sec table {{ width:100%; border-collapse:collapse; margin:16px 0; font-size:13.2px; display:block; overflow-x:auto; }}
.spec-sec thead th {{
  background:var(--navy); color:#fff; text-align:left; padding:9px 12px;
  font-size:11.5px; text-transform:uppercase; letter-spacing:.7px; border:1px solid var(--navy); white-space:nowrap;
}}
.spec-sec tbody td {{ padding:8px 12px; border:1px solid var(--line); vertical-align:top; min-width:90px; }}
.spec-sec tbody tr:nth-child(even) {{ background:#FBF9F3; }}
figure.diagram {{ margin:22px 0 26px; border:1px solid var(--line); border-radius:12px;
  overflow:hidden; background:#FDFCF8; }}
figure.diagram figcaption {{ background:linear-gradient(90deg,var(--navy-ink),var(--navy));
  padding:12px 20px; display:flex; flex-direction:column; gap:2px; }}
.dg-kicker {{ color:var(--gold); font-size:10px; text-transform:uppercase; letter-spacing:2.2px; font-weight:700; }}
.dg-title {{ color:#fff; font-family:var(--serif); font-size:16.5px; }}
.dg-cap {{ color:#ADB3D6; font-size:12px; }}
.dg-body {{ padding:20px; overflow-x:auto; }}
.dg-body svg {{ max-width:100%; height:auto; display:block; margin:0 auto; }}
#toTop {{ position:fixed; bottom:26px; right:26px; width:44px; height:44px; border-radius:50%;
  background:var(--gold); color:var(--navy-ink); border:none; font-size:20px; cursor:pointer;
  box-shadow:0 4px 14px rgba(21,27,69,.25); opacity:0; pointer-events:none; transition:opacity .25s; z-index:50; }}
#toTop.show {{ opacity:1; pointer-events:auto; }}
footer.doc-foot {{ padding:34px 56px 60px; color:var(--muted); font-size:12.5px;
  border-top:1px solid var(--line); }}
@media (max-width:1080px) {{
  .chips {{ grid-template-columns:repeat(2,1fr); }}
  nav.side {{ display:none; }}
  .content, header.hero, footer.doc-foot {{ padding-left:26px; padding-right:26px; }}
  .chips {{ margin-left:26px; margin-right:26px; }}
}}
@media print {{
  nav.side, #toTop, .nav-search {{ display:none; }}
  .spec-sec {{ break-inside:avoid-page; box-shadow:none; }}
  header.hero {{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
}}
</style>
</head>
<body>
<div class="wrap">
  <nav class="side">
    <div class="brand">
      <div class="star">✦ ✧ ✦</div>
      <h1>SITARA</h1>
      <p>Phase 1 · Specification</p>
      <span class="vtag">VERSION 3.0 · CANONICAL</span>
    </div>
    <div class="nav-search"><input id="navFilter" type="text" placeholder="Filter sections…" /></div>
    <div class="nav-list" id="navList">
      {nav_html}
    </div>
  </nav>
  <main>
    <header class="hero">
      <div class="kicker">Confidential · Canonical Baseline · v3.0 · 29 July 2026</div>
      <h2>Sitara Phase 1 — Complete Execution Specification v2</h2>
      <div class="sub">The canonical Phase-1 baseline: every historical contradiction resolved (§26 decision log), a complete UI/UX Execution Pack (§28–§31), photographic Tara, call-first communication, whole-app native language, five-layer zero-hallucination astrology, and infrastructure scaling to ten million users. One budget, one timeline, one scope — change-controlled from here.</div>
      <div class="promise">"Every morning, Tara helps you understand the energy of your day. Throughout the day, she helps you think through decisions and problems. Every night, she helps you reflect, remember and prepare for tomorrow."</div>
      <div class="meta-row">Supersedes Specification v1 · web-research-validated (astrology APIs · voice providers · avatar technology) · 16 systems diagrams · 32 sections (0–31) · zero contradictions — §26 decision log · §31 change control</div>
    </header>
    <div class="chips">{chips_html}</div>
    <div class="content">
      {''.join(body_sections)}
    </div>
    <footer class="doc-foot">
      Sitara · Phase-1 Specification v2 · prepared for the founding team &amp; board · Confidential — do not distribute.
      Companion artefacts: Specification v1, Product Blueprint, Implementation Pack, Financial Model, Competitive Dossier, Board Decks 1 &amp; 2, Research Annex (provider research with sources &amp; verification labels).
    </footer>
  </main>
</div>
<button id="toTop" title="Back to top">↑</button>
<script>
(function() {{
  var links = Array.prototype.slice.call(document.querySelectorAll('.nav-item'));
  var secs  = Array.prototype.slice.call(document.querySelectorAll('.spec-sec'));
  var obs = new IntersectionObserver(function(entries) {{
    entries.forEach(function(e) {{
      if (e.isIntersecting) {{
        links.forEach(function(l) {{ l.classList.toggle('active', l.getAttribute('href') === '#' + e.target.id); }});
      }}
    }});
  }}, {{ rootMargin:'-20% 0px -70% 0px' }});
  secs.forEach(function(s) {{ obs.observe(s); }});
  document.getElementById('navFilter').addEventListener('input', function() {{
    var q = this.value.toLowerCase().trim();
    links.forEach(function(l) {{
      var t = l.textContent.toLowerCase();
      l.classList.toggle('hidden', q && t.indexOf(q) === -1);
    }});
  }});
  var btn = document.getElementById('toTop');
  window.addEventListener('scroll', function() {{
    btn.classList.toggle('show', window.scrollY > 700);
  }});
  btn.addEventListener('click', function() {{ window.scrollTo({{top:0, behavior:'smooth'}}); }});
}})();
</script>
</body>
</html>"""

OUT.write_text(page)
print(f"wrote {OUT} ({OUT.stat().st_size/1024:.0f} KB), {len(body_sections)} sections, {sum(len(v) for v in DIAGRAMS.values())} diagrams")
