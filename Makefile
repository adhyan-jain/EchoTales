.DEFAULT_GOAL := help
.PHONY: help setup test test-research lint typecheck verify serve demo

help:
	@echo "make setup      install the workspace (scripts/setup.sh)"
	@echo "make test       stub-mode pytest (core, pipeline), then webview jest"
	@echo "make test-research  research arena tests (need torch: uv sync --extra render)"
	@echo "make verify     the one check to run before a commit (= test)"
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

# lint and typecheck are not part of verify yet: 1,397 ruff and 1,166 mypy errors on 2026-11-13.
verify: test

serve:
	uv run echotales webview-server --static-dir webview/build

demo:
	ECHOTALES_LLM_MODE=stub uv run python scripts/demo/run_demo.py
