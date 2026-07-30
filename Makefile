.PHONY: run test lint format

run:
	. .venv/bin/activate && uvicorn app.main:app --reload

test:
	. .venv/bin/activate && pytest -v

lint:
	. .venv/bin/activate && ruff check .

format:
	. .venv/bin/activate && ruff format .