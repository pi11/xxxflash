#!/bin/sh
# Download the pinned Ruffle self-hosted build into static/vendor/ruffle/.
# The pinned release tag lives in static/vendor/ruffle/VERSION (e.g. nightly-2026-09-29).
set -eu
cd "$(dirname "$0")/.."
DIR=static/vendor/ruffle
TAG=$(cat "$DIR/VERSION")
DATE=${TAG#nightly-}
NAME="ruffle-nightly-$(echo "$DATE" | tr - _)-web-selfhosted.zip"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
curl -fsSL -o "$TMP/ruffle.zip" "https://github.com/ruffle-rs/ruffle/releases/download/$TAG/$NAME"
find "$DIR" -mindepth 1 ! -name VERSION -delete
unzip -q -o "$TMP/ruffle.zip" -d "$DIR"
echo "Ruffle $TAG installed in $DIR"
