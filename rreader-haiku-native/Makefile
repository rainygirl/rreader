# Makefile -- build news.coroke.net (rreader-haiku-native) with a plain,
# direct g++ invocation rather than depending on Haiku's shared
# makefile-engine being present at a particular path, so this works the
# same whether you build inside the OS source tree or as a standalone
# third-party app. Run on an actual Haiku machine/VM (or Haiku's
# cross-compilation toolchain) -- this was NOT compiled in the session
# that wrote it; see README.md's "Not yet built" section.

APP_NAME := NewsCoroke
TARGET := $(APP_NAME)

SRC_DIR := src
OBJ_DIR := obj
SOURCES := $(wildcard $(SRC_DIR)/*.cpp)
OBJECTS := $(SOURCES:$(SRC_DIR)/%.cpp=$(OBJ_DIR)/%.o)

CXX ?= g++
CXXFLAGS := -std=c++17 -Wall -O2 -I$(SRC_DIR)
LDFLAGS := -lbe -lnetwork -ltranslation

.PHONY: all clean run resources

all: $(TARGET)

$(OBJ_DIR):
	mkdir -p $(OBJ_DIR)

$(OBJ_DIR)/%.o: $(SRC_DIR)/%.cpp | $(OBJ_DIR)
	$(CXX) $(CXXFLAGS) -c $< -o $@

$(TARGET): $(OBJECTS)
	$(CXX) $(OBJECTS) -o $(TARGET) $(LDFLAGS)
	$(MAKE) resources

# Embeds the app signature/icon/version from resources/App.rdef so Tracker
# and Deskbar show the right name/icon. `rc`/`xres` ship with Haiku's
# development tools; this step is skipped (with a warning, not a failure)
# on any other OS so `make` still produces a usable binary for inspection.
resources:
	@if command -v rc >/dev/null 2>&1; then \
		rc -o $(OBJ_DIR)/App.rsrc resources/App.rdef && \
		xres -o $(TARGET) $(OBJ_DIR)/App.rsrc && \
		mimeset -f $(TARGET); \
	else \
		echo "[warn] 'rc'/'xres' not found (not running on Haiku?) -- skipping resource embedding"; \
	fi

run: all
	./$(TARGET)

clean:
	rm -rf $(OBJ_DIR) $(TARGET)
