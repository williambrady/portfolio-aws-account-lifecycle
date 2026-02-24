.PHONY: build create-account dry-run close-account close-all-accounts shell clean help

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
ifdef EMAIL
CLI_ARGS += --email $(EMAIL)
endif

# Default target
help:
	@echo "Available targets:"
	@echo "  build              - Build the Docker image"
	@echo "  create-account     - Create a new AWS account (requires ACCOUNT_NAME)"
	@echo "  dry-run            - Show plan without making changes (requires ACCOUNT_NAME)"
	@echo "  close-account      - Close a single AWS account (dry-run by default, requires ACCOUNT_ID)"
	@echo "  close-all-accounts - Close ALL member accounts (dry-run by default)"
	@echo "  shell              - Open shell in container"
	@echo "  clean              - Remove Docker image"
	@echo ""
	@echo "Environment variables:"
	@echo "  MGMT_PROFILE       - AWS profile for management account (required if not set in config.yaml)"
	@echo "  AUTOMATION_PROFILE - AWS profile for automation account (required if not set in config.yaml)"
	@echo "  ACCOUNT_NAME       - Name for the new account (required for create-account/dry-run)"
	@echo "  EMAIL              - Use a specific email address (skips SSM unique number)"
	@echo "  ACCOUNT_ID         - Account ID to close (required for close-account)"
	@echo "  APPROVE            - Set to 'true' to actually close accounts (default: dry-run)"

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

# Build CLI args for close commands — dry-run by default, APPROVE=true to execute
CLOSE_CLI_ARGS :=
ifdef MGMT_PROFILE
CLOSE_CLI_ARGS += --mgmt-profile $(MGMT_PROFILE)
endif
ifneq ($(APPROVE),true)
CLOSE_CLI_ARGS += --dry-run
endif

# Close a single AWS account
close-account: build
ifndef ACCOUNT_ID
	$(error ACCOUNT_ID is required)
endif
	docker run --rm \
		-v "$(HOME)/.aws:/home/lifecycle/.aws:ro" \
		$(DOCKER_ENV) \
		$(IMAGE_NAME):$(IMAGE_TAG) close-account --account-id $(ACCOUNT_ID) $(CLOSE_CLI_ARGS)

# Close ALL member accounts (nuclear option)
close-all-accounts: build
	docker run --rm -it \
		-v "$(HOME)/.aws:/home/lifecycle/.aws:ro" \
		$(DOCKER_ENV) \
		$(IMAGE_NAME):$(IMAGE_TAG) close-account --all $(CLOSE_CLI_ARGS)

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
