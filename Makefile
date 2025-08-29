PY=python
PIP=pip
VENV=.venv
ACTIVATE=. $(VENV)/bin/activate;

setup:
	@test -d $(VENV) || $(PY) -m venv $(VENV)
	$(ACTIVATE) $(PIP) install --upgrade pip
	$(ACTIVATE) $(PIP) install -r requirements.txt

ui:
	$(ACTIVATE) $(PY) -m streamlit run ui/app.py -- --alarms "demo/alarms/*.json" --out outputs

demo:
	$(ACTIVATE) $(PY) -m scripts.alarm_triage.triage --alarms "demo/alarms/*.json" --out outputs/batch --offline --emit-draft

test:
	$(ACTIVATE) pytest -q

lint:
	$(ACTIVATE) ruff check . || true
	$(ACTIVATE) ruff format .

type:
	$(ACTIVATE) mypy scripts ui || true

cov:
	$(ACTIVATE) pytest --cov=scripts --cov=ui --cov-report=term-missing --cov-report=xml

clean:
	rm -rf outputs __pycache__ .pytest_cache .mypy_cache

docker-build:
	docker build -t alarm-triage-demo .

docker-run:
	docker run --rm -p 8501:8501 alarm-triage-demo

.PHONY: setup ui demo test lint type cov clean docker-build docker-run
