REPOS := \
    https://github.com/EricBoix/jj_doc_Collecting_Gold_Dust \
    https://github.com/EricBoix/jj_doc_Zen_Flesh_Zen_Bones

TESTING_DIR  := $(abspath $(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
REPO_NAMES   := $(notdir $(REPOS))

.PHONY: all pull test \
    $(addprefix pull-,$(REPO_NAMES)) \
    $(addprefix test-,$(REPO_NAMES))

all: test

pull: $(addprefix pull-,$(REPO_NAMES))

test: $(addprefix test-,$(REPO_NAMES))

define repo_rules
pull-$(notdir $(1)):
	@if [ -d "$(TESTING_DIR)/$(notdir $(1))" ]; then \
		git -C "$(TESTING_DIR)/$(notdir $(1))" pull; \
	else \
		git -C "$(TESTING_DIR)" clone $(1); \
	fi

test-$(notdir $(1)): pull-$(notdir $(1))
	cd "$(TESTING_DIR)/$(notdir $(1))/Convert" && \
	python3 -m venv venv && \
	. venv/bin/activate && \
	pip install -r requirements.txt -r requirements-dev.txt && \
	pytest test_main.py
endef

$(foreach repo,$(REPOS),$(eval $(call repo_rules,$(repo))))
