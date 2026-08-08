"""Every §-citation in the codebase resolves to a real section of SPEC.md.

A dangling citation is worse than none: this repo argues from the spec
constantly, and a reader who follows a citation to a section that does not exist
learns to distrust every other citation. Six of them shipped in one commit
before this test existed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SPEC = ROOT / "docs" / "spec" / "SPEC.md"
SEARCH_ROOTS = (
    ROOT / "services" / "api" / "src",
    ROOT / "services" / "api" / "tests",
    ROOT / "services" / "astro" / "src",
    ROOT / "services" / "realtime" / "src",
    ROOT / "packages" / "schemas" / "python",
)

#: §5.3 · §34.2 · §10-9 · §2.4-8 · §8-memory — the numeric head is the section.
CITATION = re.compile(r"§\s?(\d+(?:\.\d+)*)")


def spec_sections() -> set[str]:
    """Every id SPEC.md defines: headings and bold change-control entries."""
    text = SPEC.read_text(encoding="utf-8")
    ids: set[str] = set()
    for match in re.finditer(r"^#{1,4}\s+(\d+(?:\.\d+)*)[.\s]", text, re.MULTILINE):
        ids.add(match.group(1))
    for match in re.finditer(r"^\*\*(\d+\.\d+)\s", text, re.MULTILINE):
        ids.add(match.group(1))
    # A subsection implies its parent (§34.2 exists ⇒ §34 is citable).
    for found in list(ids):
        parts = found.split(".")
        for depth in range(1, len(parts)):
            ids.add(".".join(parts[:depth]))
    return ids


def citations() -> list[tuple[Path, int, str]]:
    rows: list[tuple[Path, int, str]] = []
    for root in SEARCH_ROOTS:
        for path in root.rglob("*.py"):
            if ".venv" in path.parts or "__pycache__" in path.parts:
                continue
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                for match in CITATION.finditer(line):
                    rows.append((path, number, match.group(1)))
        for path in root.rglob("*.json"):
            if ".venv" in path.parts:
                continue
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                for match in CITATION.finditer(line):
                    rows.append((path, number, match.group(1)))
    return rows


def test_the_spec_parses_into_sections() -> None:
    """Guard the guard: if the parser stopped finding sections, every
    citation below would 'resolve' against an empty set and fail loudly —
    but a parser that found EVERYTHING would pass vacuously."""
    sections = spec_sections()

    assert "9" in sections and "5.3" in sections and "34.2" in sections
    assert "37.2" in sections  # the entry that started this
    assert "36.4" not in sections  # the number that was cited but never existed
    assert 100 < len(sections) < 1000


def test_the_codebase_cites_sections_that_exist() -> None:
    sections = spec_sections()
    dangling = [
        f"{path.relative_to(ROOT)}:{line} cites §{ref}"
        for path, line, ref in citations()
        if ref not in sections
    ]

    assert not dangling, "dangling spec citations:\n  " + "\n  ".join(sorted(dangling))


def test_there_are_citations_to_check() -> None:
    """A search that found nothing would pass silently."""
    assert len(citations()) > 200


@pytest.mark.parametrize("doc", ["change-log.md", "../../CLAUDE.md"])
def test_the_docs_cite_sections_that_exist(doc: str) -> None:
    path = (ROOT / "docs" / doc).resolve()
    if not path.exists():
        pytest.skip(f"{doc} not present")
    sections = spec_sections()
    dangling = [
        f"§{match.group(1)}"
        for match in CITATION.finditer(path.read_text(encoding="utf-8"))
        if match.group(1) not in sections
    ]

    assert not dangling, f"{doc} cites missing sections: {sorted(set(dangling))}"
