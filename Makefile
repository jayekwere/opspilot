.PHONY: install check test build demo benchmark serve container
install:
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip==26.2.2
	.venv/bin/python -m pip install --require-hashes -r requirements-dev.lock
	npm ci --ignore-scripts
check:
	.venv/bin/ruff check opspilot tests scripts
	.venv/bin/ruff format --check opspilot tests scripts
	.venv/bin/mypy opspilot
	npm run lint
	npm run typecheck
test:
	.venv/bin/python -m pytest
build:
	npm run build
demo:
	.venv/bin/python -m opspilot.cli demo
benchmark:
	.venv/bin/python -m scripts.benchmark
serve:
	.venv/bin/python -m opspilot.cli serve
container:
	docker build --target test -t opspilot:test .
	docker run --rm --cap-drop ALL --security-opt no-new-privileges --memory 512m --cpus 1 --pids-limit 128 opspilot:test
	docker build --target runtime -t opspilot:local .
	.venv/bin/python -m scripts.container_smoke
