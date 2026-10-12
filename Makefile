# Everything runs through uv by default. If your tools are already on PATH
# (say, inside a Sprite you set up by hand), use: make check RUN=
RUN ?= uv run
PY := $(RUN) python
PORT ?= 8080
LOCAL_URL := http://127.0.0.1:$(PORT)
FLY_APP ?= $(shell sed -n 's/^app = "\(.*\)"/\1/p' app/fly.toml)
APP_URL ?= https://$(FLY_APP).fly.dev
REGIONS := iad lhr fra gru nrt syd
ANCHOR_KEY := $(or $(ANCHOR_API_KEY),$(ANCHORBROWSER_API_KEY))

.PHONY: help setup dev lint test smoke smoke-local check e2e deploy regions clean

help:
	@echo "make setup        install deps and the local Chromium"
	@echo "make dev          run the demo app on $(LOCAL_URL)"
	@echo "make check        lint + test + smoke (smoke skips without an Anchor key)"
	@echo "make smoke-local  run all three demos against a local app, no key needed"
	@echo "make deploy       deploy the app to Fly"
	@echo "make regions      one Machine in each of: $(REGIONS)"
	@echo "make e2e          run repro tests the agent wrote in e2e/"

setup:
	uv sync
	$(RUN) playwright install chromium

dev:
	cd app/src && DEMO_INBOX_TOKEN=$${DEMO_INBOX_TOKEN:-dev} $(RUN) uvicorn storefront.app:app --port $(PORT) --reload

lint:
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	$(RUN) mypy

test:
	$(PY) -m unittest discover -s tests -t . -v

# The real thing: Anchor browsers in six countries against the deployed app.
smoke:
ifeq ($(ANCHOR_KEY),)
	@echo "smoke: skipped (set ANCHOR_API_KEY to run against $(APP_URL))"
else
	$(PY) 01-region-sweep/sweep.py --url $(APP_URL) --expect-broken gru
	$(PY) 03-first-user/first_user.py --url $(APP_URL) --expect-finding blank-display-name
endif

# Same demos, local Chromium, local app. Good for working on the scripts.
smoke-local:
	@cd app/src && DEMO_INBOX_TOKEN=dev $(RUN) uvicorn storefront.app:app --port $(PORT) \
		>/dev/null 2>&1 & echo $$! > .smoke-local.pid
	@sleep 2
	@status=0; \
	$(PY) 01-region-sweep/sweep.py --url $(LOCAL_URL) --local --expect-broken gru || status=1; \
	$(PY) 02-repro/repro_agent.py --issue-file 02-repro/sample-issue.md --url $(LOCAL_URL) \
		--local --out out/repro-local --tests-dir out/repro-local/e2e || status=1; \
	$(PY) 03-first-user/first_user.py --url $(LOCAL_URL) --local --inbox-token dev \
		--expect-finding blank-display-name || status=1; \
	kill $$(cat .smoke-local.pid) 2>/dev/null; rm -f .smoke-local.pid; exit $$status

check: lint test smoke

e2e:
	APP_URL=$(APP_URL) $(PY) -m unittest discover -s e2e -t . -v

deploy:
	cd app && fly deploy

regions:
	@for r in $(REGIONS); do (cd app && fly scale count 1 --region $$r --yes); done

clean:
	rm -rf out .smoke-local.pid
