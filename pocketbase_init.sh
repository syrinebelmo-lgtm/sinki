#!/bin/bash
# PocketBase Init Script for SINKI
# Download and setup PocketBase locally (replaces Supabase)
# Run: bash pocketbase_init.sh

set -e

echo "🔧 Sinki + PocketBase Setup"
echo "================================"

# Detect OS
OS=$(uname -s)
ARCH=$(uname -m)

# Download PocketBase latest
echo "📥 Downloading PocketBase..."
if [[ "$OS" == "Darwin" ]]; then
    if [[ "$ARCH" == "arm64" ]]; then
        PB_URL="https://github.com/pocketbase/pocketbase/releases/download/v0.20.10/pocketbase_0.20.10_darwin_arm64.zip"
    else
        PB_URL="https://github.com/pocketbase/pocketbase/releases/download/v0.20.10/pocketbase_0.20.10_darwin_amd64.zip"
    fi
elif [[ "$OS" == "Linux" ]]; then
    if [[ "$ARCH" == "aarch64" ]]; then
        PB_URL="https://github.com/pocketbase/pocketbase/releases/download/v0.20.10/pocketbase_0.20.10_linux_arm64.zip"
    else
        PB_URL="https://github.com/pocketbase/pocketbase/releases/download/v0.20.10/pocketbase_0.20.10_linux_amd64.zip"
    fi
else
    echo "❌ Windows: télécharge manuellement depuis https://github.com/pocketbase/pocketbase/releases"
    exit 1
fi

# Create directory
mkdir -p pb_data
cd pb_data

# Download
curl -L "$PB_URL" -o pocketbase.zip
unzip -o pocketbase.zip
rm pocketbase.zip

cd ..

# Make executable
chmod +x pb_data/pocketbase

echo "✅ PocketBase téléchargé"
echo ""
echo "🚀 Lance PocketBase avec:"
echo "   ./pb_data/pocketbase serve"
echo ""
echo "📱 Admin panel: http://localhost:8090/_/"
echo "🔌 API: http://localhost:8090"
