# Build on Haiku. On x86_gcc2 hybrid installs the modern compiler lives in
# the x86 secondary architecture, so everything goes through `setarch x86`.

APP_NAME := NewsCoroke
TARGET := $(APP_NAME)

SRC_DIR := src
OBJ_DIR := obj
SOURCES := $(wildcard $(SRC_DIR)/*.cpp)
OBJECTS := $(SOURCES:$(SRC_DIR)/%.cpp=$(OBJ_DIR)/%.o)

ARCH := $(shell getarch 2>/dev/null)
ifeq ($(ARCH),x86_gcc2)
  CXX := setarch x86 g++
else
  CXX ?= g++
endif

# libcurl headers are vendored (8.14.1) because HaikuPorts' *_devel package
# isn't always installable; the runtime lib comes from the curl package.
CXXFLAGS := -std=c++17 -Wall -O2 -I$(SRC_DIR) -Ithird_party/curl/include
# -l:libcurl.so.4 since the unversioned libcurl.so symlink also lives in _devel.
LDFLAGS := -lbe -ltranslation -l:libcurl.so.4

INSTALL_DIR ?= /boot/home/config/non-packaged/apps

.PHONY: all clean run resources install

all: $(TARGET)

$(OBJ_DIR):
	mkdir -p $(OBJ_DIR)

$(OBJ_DIR)/%.o: $(SRC_DIR)/%.cpp | $(OBJ_DIR)
	$(CXX) $(CXXFLAGS) -c $< -o $@

$(TARGET): $(OBJECTS)
	$(CXX) $(OBJECTS) -o $(TARGET) $(LDFLAGS)
	$(MAKE) resources

resources:
	@if command -v rc >/dev/null 2>&1; then \
		rc -o $(OBJ_DIR)/App.rsrc resources/App.rdef && \
		xres -o $(TARGET) $(OBJ_DIR)/App.rsrc && \
		mimeset -f $(TARGET); \
	else \
		echo "[warn] 'rc'/'xres' not found -- skipping resource embedding"; \
	fi

install: $(TARGET)
	mkdir -p "$(INSTALL_DIR)"
	cp $(TARGET) "$(INSTALL_DIR)/news.coroke.net"
	mimeset -f "$(INSTALL_DIR)/news.coroke.net"

run: all
	./$(TARGET)

clean:
	rm -rf $(OBJ_DIR) $(TARGET)
