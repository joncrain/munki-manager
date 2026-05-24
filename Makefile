## Munki Manager — Azure deployment helpers.
##
## Prereqs: az CLI, terraform, an active `az login` against the target
## subscription. Build images server-side via `az acr build` so no local Docker
## daemon is required.
##
## Typical first-time flow:
##   1) cp terraform/terraform.tfvars.example terraform/terraform.tfvars && $EDITOR ...
##   2) make tf-init
##   3) make tf-apply        # bootstrap apply (no custom domain yet)
##   4) make deploy          # build & push images, roll containers (migrations
##                            #  run automatically on backend container start)
##   5) Cloudflare CNAME munki-manager.example.com -> $(make show-cname) (DNS only)
##   6) Cloudflare TXT  asuid.munki-manager.example.com -> <token>  (the token comes from
##      `az containerapp hostname add`'s error message — see docs/azure-deployment.md)
##   7) make tf-domain CUSTOM_DOMAIN=munki-manager.example.com
##
## Day-2: `make deploy` is enough; Terraform state is unaffected by image rolls.

SHELL := /bin/zsh
TF_DIR := terraform
TF := terraform -chdir=$(TF_DIR)

# Resolved from Terraform state at runtime so the targets work after every apply
# without you needing to remember resource names.
ACR_NAME       = $(shell $(TF) output -raw acr_name 2>/dev/null)
ACR_LOGIN      = $(shell $(TF) output -raw acr_login_server 2>/dev/null)
RG             = $(shell $(TF) output -raw resource_group 2>/dev/null)
ENV_NAME       = $(shell $(TF) output -raw container_app_environment_name 2>/dev/null)
BACKEND_APP    = $(shell $(TF) output -raw backend_app_name 2>/dev/null)
FRONTEND_APP   = $(shell $(TF) output -raw frontend_app_name 2>/dev/null)
FRONTEND_FQDN  = $(shell $(TF) output -raw frontend_default_fqdn 2>/dev/null)
# Override on the command line: `make tf-domain CUSTOM_DOMAIN=munki-manager.example.com`
CUSTOM_DOMAIN ?= $(shell $(TF) output -raw custom_domain 2>/dev/null)

# Image tag = short git SHA so revisions are reproducible. If you have
# uncommitted changes (so the SHA-tagged image you're about to push is
# different code than the previous one with the same tag), set TAG to
# something else explicitly, e.g. `make deploy TAG=$(git rev-parse --short HEAD)-dirty`.
TAG ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo manual)

# Whether to pin Container Apps to the freshly-pushed digest instead of just
# the tag. Tags don't change identity in Container Apps' eyes — pushing a new
# image with the same tag does NOT trigger a rollout because the template
# string is unchanged. ``DIGEST_PIN=1`` (the default) resolves the digest
# after `az acr build` and rolls to ``…@sha256:…``, which always replaces
# the running image. Set ``DIGEST_PIN=0`` to keep the legacy tag-only update.
DIGEST_PIN ?= 1

.PHONY: help
help:                 ## Show this help.
	@grep -E '^[a-zA-Z0-9_.-]+:.*?##' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?##"} {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Terraform --------------------------------------------------------------

.PHONY: tf-init
tf-init:              ## Initialize Terraform providers.
	$(TF) init

.PHONY: tf-plan
tf-plan:              ## Plan against current tfvars.
	$(TF) plan

.PHONY: tf-apply
tf-apply:             ## First apply (no custom domain). Creates everything else.
	$(TF) apply

.PHONY: tf-domain
tf-domain:            ## Bind custom domain + issue managed cert. Run after Cloudflare CNAME + asuid TXT records are in place. See docs/azure-deployment.md.
	@test -n "$(FRONTEND_APP)" || (echo "Apps not provisioned yet — run 'make tf-apply' first." && exit 1)
	@test -n "$(CUSTOM_DOMAIN)" || (echo "Set CUSTOM_DOMAIN, e.g. 'make tf-domain CUSTOM_DOMAIN=munki-manager.example.com'" && exit 1)
	@echo ">>> Step 1: bind hostname (no cert yet) — requires asuid TXT in DNS"
	@if az containerapp show -g $(RG) -n $(FRONTEND_APP) --query "properties.configuration.ingress.customDomains[?name=='$(CUSTOM_DOMAIN)']" -o tsv | grep -q .; then \
		echo "    hostname already bound — skipping"; \
	else \
		az containerapp hostname add -g $(RG) -n $(FRONTEND_APP) --hostname $(CUSTOM_DOMAIN); \
	fi
	@echo ">>> Step 2: issue managed cert (CNAME-validated)"
	@CERT_NAME="cert-$$(echo $(CUSTOM_DOMAIN) | tr . -)"; \
	if az containerapp env certificate show -g $(RG) --name $(ENV_NAME) --certificate $$CERT_NAME >/dev/null 2>&1; then \
		echo "    cert $$CERT_NAME already exists — skipping create"; \
	else \
		az containerapp env certificate create -g $(RG) --name $(ENV_NAME) \
			--certificate-name $$CERT_NAME \
			--hostname $(CUSTOM_DOMAIN) --validation-method CNAME; \
	fi
	@echo ">>> Step 2b: wait for cert to reach Succeeded (managed cert issuance is asynchronous, ~1-5 min)"
	@for i in $$(seq 1 30); do \
		STATE=$$(az containerapp env certificate list -g $(RG) --name $(ENV_NAME) --query "[?properties.subjectName=='$(CUSTOM_DOMAIN)'].properties.provisioningState | [0]" -o tsv); \
		printf "    [%2d/30] cert state: %s\n" $$i "$$STATE"; \
		if [ "$$STATE" = "Succeeded" ]; then break; fi; \
		if [ "$$STATE" = "Failed" ]; then \
			echo "ERROR: cert provisioning failed. Check 'az containerapp env certificate show -g $(RG) --name $(ENV_NAME) --certificate cert-$$(echo $(CUSTOM_DOMAIN) | tr . -)'"; \
			exit 1; \
		fi; \
		sleep 10; \
	done
	@STATE=$$(az containerapp env certificate list -g $(RG) --name $(ENV_NAME) --query "[?properties.subjectName=='$(CUSTOM_DOMAIN)'].properties.provisioningState | [0]" -o tsv); \
	if [ "$$STATE" != "Succeeded" ]; then echo "ERROR: cert did not reach Succeeded within 5 min (last state: $$STATE)"; exit 1; fi
	@echo ">>> Step 3: bind cert to hostname"
	@CERT_ID=$$(az containerapp env certificate list -g $(RG) --name $(ENV_NAME) --query "[?properties.subjectName=='$(CUSTOM_DOMAIN)'].id | [0]" -o tsv); \
		az containerapp hostname bind -g $(RG) -n $(FRONTEND_APP) --hostname $(CUSTOM_DOMAIN) \
			--environment $(ENV_NAME) --certificate "$$CERT_ID"
	@echo ">>> Done. Visit https://$(CUSTOM_DOMAIN)"

.PHONY: tf-destroy
tf-destroy:           ## Tear down all Azure resources.
	$(TF) destroy

.PHONY: tf-output
tf-output:            ## Show all Terraform outputs.
	$(TF) output

.PHONY: show-cname
show-cname:           ## Print the Container Apps default FQDN to use as the Cloudflare CNAME target.
	@echo "Cloudflare DNS: CNAME $$($(TF) output -raw custom_domain_url 2>/dev/null | sed 's|https://||') -> $(FRONTEND_FQDN) (Proxy: DNS only / gray cloud)"

# --- Image build & deploy ---------------------------------------------------

.PHONY: build-backend
build-backend:        ## Build & push backend image to ACR (server-side, no local Docker).
	@test -n "$(ACR_NAME)" || (echo "ACR not provisioned yet — run 'make tf-apply' first." && exit 1)
	az acr build --registry $(ACR_NAME) \
		--image munki-manager-backend:$(TAG) \
		--image munki-manager-backend:latest \
		--file backend/Dockerfile backend

.PHONY: build-frontend
build-frontend:       ## Build & push frontend image to ACR.
	@test -n "$(ACR_NAME)" || (echo "ACR not provisioned yet — run 'make tf-apply' first." && exit 1)
	az acr build --registry $(ACR_NAME) \
		--image munki-manager-frontend:$(TAG) \
		--image munki-manager-frontend:latest \
		--build-arg VITE_BUILD_SHA=$(TAG) \
		--file frontend/Dockerfile frontend

.PHONY: build
build: build-backend build-frontend  ## Build & push both images.

.PHONY: roll
roll:                 ## Roll both Container Apps to TAG (default: short git sha). Pins to digest when DIGEST_PIN=1 (default) so same-tag rebuilds always roll out. Does not rebuild.
	@test -n "$(BACKEND_APP)"  || (echo "Apps not provisioned yet — run 'make tf-apply' first." && exit 1)
ifeq ($(DIGEST_PIN),1)
	@BACKEND_DIGEST=$$(az acr repository show --name $(ACR_NAME) --image munki-manager-backend:$(TAG) --query digest -o tsv); \
		FRONTEND_DIGEST=$$(az acr repository show --name $(ACR_NAME) --image munki-manager-frontend:$(TAG) --query digest -o tsv); \
		if [ -z "$$BACKEND_DIGEST" ] || [ -z "$$FRONTEND_DIGEST" ]; then \
			echo "Could not resolve digests for tag $(TAG); aborting"; exit 1; \
		fi; \
		echo "Pinning backend  -> $(ACR_LOGIN)/munki-manager-backend@$$BACKEND_DIGEST"; \
		echo "Pinning frontend -> $(ACR_LOGIN)/munki-manager-frontend@$$FRONTEND_DIGEST"; \
		az containerapp update -g $(RG) -n $(BACKEND_APP)  --image "$(ACR_LOGIN)/munki-manager-backend@$$BACKEND_DIGEST"   --output none; \
		az containerapp update -g $(RG) -n $(FRONTEND_APP) --image "$(ACR_LOGIN)/munki-manager-frontend@$$FRONTEND_DIGEST" --output none
else
	az containerapp update -g $(RG) -n $(BACKEND_APP)  --image $(ACR_LOGIN)/munki-manager-backend:$(TAG)  --output none
	az containerapp update -g $(RG) -n $(FRONTEND_APP) --image $(ACR_LOGIN)/munki-manager-frontend:$(TAG) --output none
endif
	@echo "Rolled to tag: $(TAG) (digest_pin=$(DIGEST_PIN))"

.PHONY: deploy
deploy: build roll    ## Build, push, and roll both apps in one shot.

.PHONY: migrate
migrate:              ## Manually run Alembic migrations in a running backend replica. Normally not needed: backend/entrypoint.sh auto-runs `alembic upgrade head` on every container start, so `make deploy` already migrates as the new revision rolls out. Use this only for ad-hoc fixups (or when RUN_MIGRATIONS_ON_START=false).
	@test -n "$(BACKEND_APP)" || (echo "Backend not provisioned." && exit 1)
	az containerapp exec -g $(RG) -n $(BACKEND_APP) --command "alembic upgrade head"

# --- Day-2 ops --------------------------------------------------------------

.PHONY: logs-backend
logs-backend:         ## Tail backend logs.
	az containerapp logs show -g $(RG) -n $(BACKEND_APP) --follow --tail 100

.PHONY: logs-frontend
logs-frontend:        ## Tail frontend logs.
	az containerapp logs show -g $(RG) -n $(FRONTEND_APP) --follow --tail 100

.PHONY: shell-backend
shell-backend:        ## Open a shell in a running backend replica (for ad-hoc psql, alembic, etc).
	az containerapp exec -g $(RG) -n $(BACKEND_APP) --command /bin/bash

.PHONY: psql
psql:                 ## Open psql against the production database. Requires you to know the postgres password.
	@PGFQDN=$$($(TF) output -raw postgres_fqdn) ; \
	read -s "PGPASSWORD?Postgres password: " ; echo ; \
	PGPASSWORD=$$PGPASSWORD psql "host=$$PGFQDN port=5432 user=munkiadmin dbname=automunki sslmode=require"
