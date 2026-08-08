"""The Layer-A deterministic engine (SPEC §5.2).

Pure computation: pyswisseph behind one locked gateway (ephemeris.py), IANA
tzdb for all timezone maths (tzresolve.py), and typed FactSnapshot emission
(factbuild.py). The LLM never computes astrology — it only cites these facts.
"""
