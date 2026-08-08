"""Numerology engine (SPEC §5, §22.10) — Chaldean primary, Pythagorean secondary.

Deterministic like the astrology engine: the LLM never computes a number and
never produces lucky numbers outside this engine (§5.3). Chaldean values are
defined over the user-CONFIRMED Latin transliteration of the name as spoken
(§22.10) — never over a guess.
"""
