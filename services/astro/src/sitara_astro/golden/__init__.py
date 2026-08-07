"""Golden-set validation harness (SPEC §5.5, playbook P3b).

Case format, parity evaluation against the release thresholds, and the reviewer
CLI. The engine is not trusted until a human verifies expected values against
Jagannatha Hora / Drik Panchang — nothing in this package may set a case to
`verified` except an explicit, named sign-off through `cli.verify`.
"""
