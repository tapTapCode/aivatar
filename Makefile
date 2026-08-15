.PHONY: install test lint migrate api frontend frontend-test demo benchmark

install:
	python -m pip install -e '.[dev]'

test:
	pytest

lint:
	ruff check .

migrate:
	alembic upgrade head

api:
	uvicorn src.api.main:app --host 127.0.0.1 --port 8001

frontend:
	npm --prefix frontend run dev

frontend-test:
	npm --prefix frontend test

demo:
	python -m scripts.generate_demo --project examples/three-format-project.json

benchmark:
	python -m benchmarks.run --device cuda:0 --gpu-profile rtx5090 --output-dir benchmark-results/rtx5090

