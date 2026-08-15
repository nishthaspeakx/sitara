"""What the journal search IS and is not, asserted rather than assumed.

§30.5 specifies P0 search as "keyword+filters … over Journal+thread **via Atlas
Search**". M10 ships the keyword+filters contract and does **not** ship an
Atlas `$search` backend. This file is the honest marker, in the shape
`tests/voice/test_streaming_provenance.py` established: a skipping test whose
existence is the record, so the gap is visible in a test run rather than
discovered in production.

**Why the Atlas backend is deferred rather than written blind.** A `$search`
stage needs a search index, and `createSearchIndexes` does not exist on the
Community mongo §6 gives development — so an Atlas implementation could not
have been run even once before shipping. The failure mode of writing it anyway
is specific and bad: a capability probe would select it in production, on the
first real query, against an index nothing creates. An unverified path that
only ever executes in front of users is worse than one honest path and a named
gap. (This is the lesson `tests/voice/` paid for: streaming shipped UNVERIFIED
and the first live call found that Sonic requires `context_id`.)

**What is lost by deferring it, precisely.** Nothing about correctness: the P0
contract is every artefact containing every term, newest first, and
`ExactTextSearch` satisfies it exactly. What is lost is the index — the scan is
capped at `DEFAULT_SCAN_LIMIT` rows per source and LOGS when it truncates, so
a heavy journal returns incomplete results and says so in the logs rather than
pretending. That is a scale ceiling, and it is the thing to fix before the
journal gets big, not before it works.
"""

from __future__ import annotations

import pytest

from sitara_api.journal import search as journal_search


def test_there_is_exactly_one_journal_search_backend() -> None:
    """Fails the day someone adds a second one without updating this record."""
    backends = [
        name
        for name in dir(journal_search)
        if name.endswith("Search") and name not in {"JournalSearch"}
    ]
    assert backends == ["ExactTextSearch"], (
        "a second backend means §30.5's Atlas half landed — update this file, "
        "the module docstring and services/api/CLAUDE.md, and delete the skip below"
    )


@pytest.mark.skip(
    reason=(
        "§30.5's Atlas Search backend is NOT built (M10). Community mongo has no "
        "createSearchIndexes, so it could not be verified before shipping; the "
        "keyword+filters contract is met by ExactTextSearch. Unskip when an Atlas "
        "deployment and a search-index spec exist."
    )
)
def test_atlas_backend_matches_the_exact_backend_over_one_corpus() -> None:  # pragma: no cover
    """The parity test the Atlas backend must arrive with.

    Same corpus, same query, same filters, same order — the discipline
    `ExactVectorSearch` follows against `AtlasVectorSearch`. A backend that
    returned a different set would mean a user's search results depended on
    which deployment answered.
    """
    raise AssertionError("unreachable while skipped")


def test_the_scan_cap_is_declared_and_not_silent() -> None:
    """A cap nobody can see reads to a user as "nothing more matched"."""
    assert journal_search.DEFAULT_SCAN_LIMIT > 0
    source = journal_search.__file__
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "truncated" in text, "exceeding the cap must log, not shrug"
