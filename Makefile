.DEFAULT_GOAL := help
.PHONY: help setup test test-research lint typecheck lint-ratchet verify serve demo

help:
	@echo "make setup      install the workspace (scripts/setup.sh)"
	@echo "make test       stub-mode pytest (core, pipeline), then webview jest"
	@echo "make test-research  research arena tests (need torch: uv sync --extra render)"
	@echo "make verify     the one check to run before a commit (= test + lint-ratchet)"
	@echo "make lint-ratchet  fail if the ruff or mypy error count rose above scripts/maintenance/lint_baseline.json"
	@echo "make lint       ruff check ."
	@echo "make typecheck  mypy on core and pipeline"
	@echo "make serve      run the webview server against webview/build"
	@echo "make demo       run the stub-mode demo (scripts/demo/run_demo.py)"

setup:
	scripts/setup.sh

test:
	ECHOTALES_LLM_MODE=stub uv run python -m pytest packages/core/tests packages/pipeline/tests -o addopts="" -q
	cd webview && CI=true npm test -- --watchAll=false

# Separate from test: one arena experiment imports torch, which a plain `uv sync` does not install.
test-research:
	ECHOTALES_LLM_MODE=stub uv run python -m pytest packages/research/tests -o addopts="" -q

lint:
	uv run ruff check .

typecheck:
	uv run mypy packages/core/src packages/pipeline/src

# lint and typecheck cannot gate on zero (545 ruff and 1,628 mypy errors on 2026-11-20), so verify runs a ratchet:
# the count may fall (run `uv run python scripts/maintenance/lint_ratchet.py --update` and commit) and may not rise.
lint-ratchet:
	uv run python scripts/maintenance/lint_ratchet.py

verify: test lint-ratchet

serve:
	uv run echotales webview-server --static-dir webview/build

demo:
	ECHOTALES_LLM_MODE=stub uv run python scripts/demo/run_demo.py
