#!/bin/sh
set -eu
umask 077

scripts=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
applications="$HOME/Applications"
name=RepliesOwedExporter
destination="$applications/$name.app"
if [ -e "$destination" ] || [ -L "$destination" ]; then
    echo "Move the existing $destination aside before rebuilding." >&2
    exit 1
fi
/Library/Developer/CommandLineTools/usr/bin/python3 -I -S -c 'import sqlite3, zoneinfo'
mkdir -p "$applications"
build=$(mktemp -d "$applications/.replies-owed-build.XXXXXXXX")
trap 'rm -rf "$build"' EXIT
bundle="$build/$name.app"
mkdir -p "$bundle/Contents/MacOS"

# Compile the reviewed source into the executable covered by the code signature.
/usr/bin/xxd -i < "$scripts/export_replies_owed.py" > "$build/export_replies_owed.inc"
/usr/bin/clang -Wall -Wextra -Werror -I "$build" "$scripts/replies_owed_launcher.c" \
    -o "$bundle/Contents/MacOS/$name"
cat > "$bundle/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key><string>RepliesOwedExporter</string>
    <key>CFBundleIdentifier</key><string>com.rquinonez.RepliesOwedExporter</string>
    <key>CFBundleName</key><string>RepliesOwedExporter</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleVersion</key><string>1</string>
    <key>LSBackgroundOnly</key><true/>
</dict>
</plist>
PLIST
/usr/bin/codesign --force --sign - --options runtime "$bundle"
/usr/bin/codesign --verify --strict "$bundle"
mv "$bundle" "$destination"
echo "$destination"
