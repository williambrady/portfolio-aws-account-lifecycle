.PHONY: build create-account dry-run shell clean help

IMAGE_NAME := portfolio-aws-account-lifecycle
IMAGE_TAG := dev

DOCKER_ENV :=
ifdef MGMT_PROFILE
DOCKER_ENV += -e MGMT_PROFILE=$(MGMT_PROFILE)
endif
ifdef AUTOMATION_PROFILE
DOCKER_ENV += -e AUTOMATION_PROFILE=$(AUTOMATION_PROFILE)
endif

# Build CLI args for profile passthrough
CLI_ARGS :=
ifdef MGMT_PROFILE
CLI_ARGS += --mgmt-profile $(MGMT_PROFILE)
endif
ifdef AUTOMATION_PROFILE
CLI_ARGS += --automation-profile $(AUTOMATION_PROFILE)
endif

# Default target
help:
	@echo "Available targets:"
	@echo "  build          - Build the Docker image"
	@echo "  create-account - Create a new AWS account (requires ACCOUNT_NAME)"
	@echo "  dry-run        - Show plan without making changes (requires ACCOUNT_NAME)"
	@echo "  shell          - Open shell in container"
	@echo "  clean          - Remove Docker image"
	@echo ""
	@echo "Environment variables:"
	@echo "  MGMT_PROFILE       - AWS profile for management account (required)"
	@echo "  AUTOMATION_PROFILE - AWS profile for automation account (required)"
	@echo "  ACCOUNT_NAME       - Name for the new account (required for create-account/dry-run)"

# Build the Docker image
build:
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

# Create a new AWS account
create-account: build
ifndef ACCOUNT_NAME
	$(error ACCOUNT_NAME is required)
endif
	docker run --rm \
		-v "$(HOME)/.aws:/home/lifecycle/.aws:ro" \
		$(DOCKER_ENV) \
		$(IMAGE_NAME):$(IMAGE_TAG) create-account $(ACCOUNT_NAME) $(CLI_ARGS)

# Dry run - show plan without making changes
dry-run: build
ifndef ACCOUNT_NAME
	$(error ACCOUNT_NAME is required)
endif
	docker run --rm \
		-v "$(HOME)/.aws:/home/lifecycle/.aws:ro" \
		$(DOCKER_ENV) \
		$(IMAGE_NAME):$(IMAGE_TAG) create-account $(ACCOUNT_NAME) --dry-run $(CLI_ARGS)

# Open interactive shell in container
shell: build
	docker run --rm -it \
		-v "$(HOME)/.aws:/home/lifecycle/.aws:ro" \
		$(DOCKER_ENV) \
		--entrypoint /bin/bash \
		$(IMAGE_NAME):$(IMAGE_TAG)

# Clean up Docker image
clean:
	docker rmi $(IMAGE_NAME):$(IMAGE_TAG) 2>/dev/null || true
