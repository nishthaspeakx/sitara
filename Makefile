# Sitara — dev entry points. The stack is docker compose; the services you are
# actively editing run from source via .claude/launch.json (live reload).
.PHONY: dev-up dev-check test lint gates

dev-up:            ## rebuild any stale image, then bring the stack up
	@./infra/dev-up.sh

dev-check:         ## report image staleness against git HEAD (exit 1 if stale)
	@./infra/dev-up.sh --check

test:
	@cd services/api && uv run pytest -q

lint:
	@cd services/api && uv run ruff check . && uv run pyright

gates:             ## §31.7 gates only a human can close
	@cd services/api && uv run python -m sitara_api.release_gates
