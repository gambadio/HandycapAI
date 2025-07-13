#!/usr/bin/env bash
# macOS notarisation helper – fill in your Developer ID credentials.

set -e

APP="dist/HandycapAI.app"
ZIP="HandycapAI.zip"
BUNDLE_ID="com.handycapai.app"
DEV_ACCT="your@appleid.com"
TEAM_ID="XXXXXXXXXX"

# Zip the bundle
ditto -c -k --keepParent "$APP" "$ZIP"

# Upload for notarisation
xcrun altool --notarize-app \
  --file "$ZIP" \
  --primary-bundle-id "$BUNDLE_ID" \
  --username "$DEV_ACCT" \
  --team-id "$TEAM_ID" \
  --password "@keychain:AC_PASSWORD"

echo "Uploaded. Check status with:"
echo "xcrun altool --notarization-info <request-id> -u $DEV_ACCT -p @keychain:AC_PASSWORD"