# Sitara ✦

**Tara, the astrology-first AI life guide.** A premium AI life-guidance companion for affluent Indians and Indian-origin families worldwide — morning brief · Ask Tara · night reflection, grounded in a deterministic Vedic astrology engine, in the user's own language, spoken by a regionally authentic Tara.

> *"Every morning, Tara helps you understand the energy of your day. Throughout the day, she helps you think through decisions and problems. Every night, she helps you reflect, remember and prepare for tomorrow."*

**Taglines** — Sitara: *"Your stars, understood."* · Tara: *"The friend who knows your stars."*

## ⭐ Start here

**[`06-phase1-canonical/`](06-phase1-canonical/) — Phase 1 Canonical Specification v3.0** is the single source of truth for the build. Everything else in this repo is the research and decision trail that led to it. Open `Sitara_Phase1_Canonical_Spec_v3.html` in a browser for the interactive version (sidebar navigation, 15 embedded system diagrams).

## Repository map

| Folder | Contents | Status |
|---|---|---|
| `01-research/` | 20-idea market research report (Edition 2): segments, scoring, comparison, why Sitara won | Reference |
| `02-board-pack/` | Board decks 1 & 2 (PPTX+PDF), 17-sheet financial model (XLSX, live formulas), investment memo, board summary + `src/` build scripts | Reference — ⚠ financial model reflects the pre-v3 plan (₹1.45Cr/18wk); v3 baseline is ₹2.34Cr/22wk, workbook update pending |
| `03-competitive/` | 28-competitor dossier, feature matrix, threat tiers, white-space analysis | Reference |
| `04-blueprint/` | Master product blueprint + 13-file implementation pack (PRD, architecture, SQL schema, API spec, prompts, safety, analytics, test plan) | Partially superseded — stack decisions replaced by canonical spec §6 (Next.js/FastAPI/MongoDB); product philosophy carries forward |
| `05-phase1-superseded/` | Phase-1 spec v1 (Expo/NestJS/Postgres era) and the v2.2 archive | Superseded — kept for the decision trail (see canonical §26 decision log) |
| `06-phase1-canonical/` | **Canonical Spec v3.0** (MD + interactive HTML + DOCX), research annex with sources, 15 Mermaid/SVG diagrams, HTML build script | **CANONICAL** |

## The locked baseline (v3.0, §26.2)

- **Launch:** English · Hinglish · Hindi complete end-to-end; waves to 8 languages by ≈May 2027. A language ships 100% complete or not at all.
- **Tara:** photographic presence (licensed face model, portraits + cinemagraphs), phone-call experience, WhatsApp-familiar chat, "Tara · AI guide" disclosure permanent.
- **Astrology:** internal Swiss Ephemeris engine + DivineAPI + Prokerala cross-check, 10K-case golden set (CI-gated ≥99.9%), 5-state confidence, zero-hallucination contract.
- **Stack:** Next.js 15 PWA · Python FastAPI · MongoDB Atlas · AWS ap-south-1 · Play Store TWA at launch, iOS app M+2.
- **Timeline:** 22 weeks — build starts 10 Aug 2026, closed beta W17, public launch W22 (mid-Jan 2027).
- **Budget:** ₹2.34Cr baseline; AI+voice unit ceiling ₹110/paid user/month.

Any change to the baseline requires a §31.3 change-control entry in the canonical spec's §26.1 decision log.

---
*Confidential — Ivypods / Sitara founding team & board. Do not distribute.*
