.PHONY: setup test run check clean-artifacts

setup:
	@NEEDS_RECREATE=0; \
	if [ ! -x .venv/bin/python ]; then \
		NEEDS_RECREATE=1; \
	elif ! .venv/bin/python -c "import xml.parsers.expat, ensurepip, pip" >/dev/null 2>&1; then \
		echo "Existing .venv is unhealthy; recreating"; \
		NEEDS_RECREATE=1; \
	else \
		echo "Using existing .venv"; \
	fi; \
	if [ $$NEEDS_RECREATE -eq 1 ]; then \
		rm -rf .venv; \
		if [ -x /opt/homebrew/opt/python@3.13/bin/python3.13 ]; then \
			PYTHON_BIN=/opt/homebrew/opt/python@3.13/bin/python3.13; \
		else \
			PYTHON_BIN=$$(command -v python3.13 || command -v python3); \
		fi; \
		echo "Creating .venv with $$PYTHON_BIN"; \
		$$PYTHON_BIN -m venv .venv; \
	fi
	. .venv/bin/activate && python -m pip install --upgrade pip && pip install -r requirements.txt

check:
	. .venv/bin/activate && python scripts/check_api.py

test:
	. .venv/bin/activate && pytest

run:
	. .venv/bin/activate && python agent_app.py "What time is it right now?"

clean-artifacts:
	rm -f microsoft-agent-framework-0.0.1-beta.tgz
	rm -rf __pycache__ .pytest_cache

