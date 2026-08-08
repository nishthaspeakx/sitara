"""§31.7 gates that only a human can close, reported honestly."""

from sitara_api import release_gates
from sitara_api.release_gates import Stage, gates, main


def test_every_gate_names_the_section_that_mandates_it() -> None:
    for gate in gates():
        assert "§" in gate.spec_ref, gate.id
        assert gate.detail


def test_the_helpline_table_blocks_closed_beta_until_it_exists() -> None:
    """§22.9: a helpline number is a fact. Until a human has verified every
    one, the gate stays open and says so."""
    gate = next(g for g in gates() if g.id == "safety.helpline_table")

    assert gate.blocks is Stage.CLOSED_BETA
    if release_gates.HELPLINE_TABLE.exists():
        assert not gate.open
    else:
        assert gate.open
        assert "awaiting human-verified numbers" in gate.status


def test_the_corpora_report_their_own_review_status() -> None:
    """The status is read from the artefact, never from a checklist someone
    remembered to edit."""
    for gate_id in ("safety.l1_rule_lexicon", "safety.fear_selling_corpus"):
        gate = next(g for g in gates() if g.id == gate_id)
        assert gate.open
        assert "§14 named native reviewer" in gate.status


def test_a_plain_report_never_fails_a_dev_build(capsys) -> None:  # noqa: ANN001
    assert main([]) == 0
    assert "OPEN" in capsys.readouterr().out


def test_enforcing_a_stage_fails_while_gates_are_open(capsys) -> None:  # noqa: ANN001
    assert main(["--stage", "closed_beta"]) == 1
    assert "block closed_beta" in capsys.readouterr().out
