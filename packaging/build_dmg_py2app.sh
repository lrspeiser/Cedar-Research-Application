#!/bin/bash

# Build CedarPy .app and DMG for macOS using py2app

set -e  # Exit on error

PROJ_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJ_ROOT"

echo "Building CedarPy macOS app with py2app..."

# Clean up any previous builds
rm -rf build dist *.egg-info 2>/dev/null || true

# Install py2app if not already installed
pip install -q py2app

# Run py2app with the setup file
python packaging/py2app_setup.py py2app --dist-dir dist

# Check if the app was created successfully
if [ ! -d "dist/CedarPy.app" ]; then
    echo "Error: CedarPy.app was not created"
    exit 1
fi

echo "App bundle created at dist/CedarPy.app"

# Create a DMG from the app bundle
DMG_NAME="CedarPy.dmg"
DMG_PATH="$PROJ_ROOT/dist/$DMG_NAME"

# Remove old DMG if it exists
rm -f "$DMG_PATH"

# Create a temporary directory for DMG contents
TEMP_DIR="$(mktemp -d)"
trap "rm -rf $TEMP_DIR" EXIT

# Copy the app to the temp directory
cp -R "dist/CedarPy.app" "$TEMP_DIR/"

# Create symbolic link to Applications folder
ln -s /Applications "$TEMP_DIR/Applications"

# Create the DMG
echo "Creating DMG..."
hdiutil create -volname "CedarPy" \
    -srcfolder "$TEMP_DIR" \
    -ov -format UDZO \
    "$DMG_PATH"

# Get file size in MB
SIZE=$(du -h "$DMG_PATH" | cut -f1)

echo "========================================="
echo "Build completed successfully!"
echo "DMG created at: $DMG_PATH"
echo "DMG size: $SIZE"
echo "========================================="
echo ""
echo "To install:"
echo "1. Open the DMG: open \"$DMG_PATH\""
echo "2. Drag CedarPy.app to the Applications folder"
echo "3. Eject the DMG"
echo "4. Run from Applications or Spotlight"