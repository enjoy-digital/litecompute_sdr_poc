# Compiler and flags
CXX = g++
CXXFLAGS = -I. -Iimgui -Iimgui/backends -I/usr/include/SDL2 \
           -DIMGUI_IMPL_OPENGL_LOADER_GLAD -Wall -std=c++11
# Libraries
LIBS = -lSDL2 -lGL -ldl  # On Linux/macOS

# Source files
SOURCES = main.cpp \
    kiss_fft.c \
    imnodes.cpp \
	imgui/imgui.cpp \
	imgui/imgui_draw.cpp \
	imgui/imgui_demo.cpp \
	imgui/imgui_tables.cpp \
    imgui/imgui_widgets.cpp \
	imgui/backends/imgui_impl_sdl2.cpp \
	imgui/backends/imgui_impl_opengl3.cpp

# Output directory and executable name
BUILD_DIR = build
TARGET = $(BUILD_DIR)/sdr_gui

# Build target
all: $(TARGET)

# Compile and link
$(TARGET): $(SOURCES) | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) $(SOURCES) $(LIBS) -o $(TARGET)

# Create build directory if it doesn't exist
$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

# Clean build files
clean:
	rm -rf $(BUILD_DIR)

# Phony targets (not actual files)
.PHONY: all clean
