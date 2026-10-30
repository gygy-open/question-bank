#!/usr/bin/env bash
# Post-process the PyInstaller macOS build (dist/*.app) into a distributable DMG.
#
# Usage (from backend/):  deploy/macos/package.sh <sign|smoke|dmg|notarize|all>
#
#   sign      Developer ID sign (hardened runtime) when MACOS_SIGN_IDENTITY is set,
#             otherwise ad-hoc sign (enough for Apple Silicon to run it locally).
#   smoke     Launch the bundled binary in server mode and probe the API + SPA.
#   dmg       Build dist/QuestionBank-<version>-macos-<arch>.dmg (signed if an identity is set).
#   notarize  Submit the DMG to Apple and staple the ticket. Skipped unless the
#             APPLE_API_KEY_PATH / APPLE_API_KEY_ID / APPLE_API_ISSUER_ID variables are set.
#   all       sign + smoke + dmg + notarize
#
# Optional environment:
#   APP                  path to the .app (default: the single dist/*.app)
#   MACOS_SIGN_IDENTITY  e.g. "Developer ID Application: Name (TEAMID)" (must be in a keychain)
#   VERSION / ARCH       override the DMG name parts (default: Info.plist / uname -m)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ENTITLEMENTS="$HERE/entitlements.plist"
DIST="${DIST:-dist}"

if [[ -z "${APP:-}" ]]; then
  apps=("$DIST"/*.app)
  if [[ ${#apps[@]} -ne 1 || ! -d "${apps[0]}" ]]; then
    echo "error: expected exactly one .app in $DIST (set APP=...)" >&2
    exit 1
  fi
  APP="${apps[0]}"
fi
APP_NAME="$(basename "$APP" .app)"
PLIST="$APP/Contents/Info.plist"
VERSION="${VERSION:-$(/usr/libexec/PlistBuddy -c 'Print :QBFullVersion' "$PLIST" 2>/dev/null || echo 0.0.0)}"
ARCH="${ARCH:-$(uname -m)}"
DMG="$DIST/${APP_NAME// /-}-${VERSION}-macos-${ARCH}.dmg"
IDENTITY="${MACOS_SIGN_IDENTITY:-}"

sign_one() {
  codesign --force --timestamp --options runtime --entitlements "$ENTITLEMENTS" --sign "$IDENTITY" "$1"
}

cmd_sign() {
  if [[ -z "$IDENTITY" ]]; then
    echo "==> No MACOS_SIGN_IDENTITY: ad-hoc signing $APP"
    codesign --force --deep --sign - "$APP"
  else
    echo "==> Signing $APP with \"$IDENTITY\""
    # Inside-out: every Mach-O file first, then nested bundles (deepest first), then the app.
    while IFS= read -r -d '' f; do
      if file -b "$f" | grep -q "Mach-O"; then
        sign_one "$f"
      fi
    done < <(find "$APP/Contents" -type f ! -path "*/Contents/MacOS/*" -print0)
    while IFS= read -r bundle; do
      sign_one "$bundle"
    done < <(find "$APP/Contents" -type d \( -name "*.framework" -o -name "*.app" \) | awk '{ print length, $0 }' | sort -rn | cut -d" " -f2-)
    sign_one "$APP"
  fi
  codesign --verify --deep --strict --verbose=2 "$APP"
}

cmd_smoke() {
  local exe="$APP/Contents/MacOS/question-bank"
  local data port pid ok=0
  data="$(mktemp -d)"
  port="${SMOKE_PORT:-18765}"
  echo "==> Smoke test: $exe --server on :$port (data: $data)"
  # Own process group + own log: killing only the server would orphan its worker child,
  # which would keep this script's stdout (and the CI step) open.
  set -m
  DATA_DIR="$data" HOST=127.0.0.1 PORT="$port" OPEN_UI=0 "$exe" --server >"$data/stdout.log" 2>&1 &
  pid=$!
  set +m
  for _ in $(seq 1 150); do
    if ! kill -0 "$pid" 2>/dev/null; then
      break
    fi
    if curl -fsS "http://127.0.0.1:$port/api/v1/system/version"; then
      echo
      if curl -fsS "http://127.0.0.1:$port/" | grep -qi "<html"; then
        ok=1
      else
        echo "error: API is up but the bundled SPA was not served" >&2
      fi
      break
    fi
    sleep 2
  done
  kill -TERM -- "-$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  if [[ $ok -ne 1 ]]; then
    echo "error: smoke test failed; output:" >&2
    cat "$data/stdout.log" "$data/logs/app.log" >&2 2>/dev/null || true
    exit 1
  fi
  rm -rf "$data"
  echo "==> Smoke test passed"
}

cmd_dmg() {
  local staging
  staging="$(mktemp -d)"
  echo "==> Building $DMG"
  ditto "$APP" "$staging/$APP_NAME.app"
  ln -s /Applications "$staging/Applications"
  rm -f "$DMG"
  hdiutil create -volname "$APP_NAME" -srcfolder "$staging" -fs HFS+ -format UDZO -ov "$DMG"
  rm -rf "$staging"
  if [[ -n "$IDENTITY" ]]; then
    codesign --force --timestamp --sign "$IDENTITY" "$DMG"
  fi
}

cmd_notarize() {
  if [[ -z "${APPLE_API_KEY_PATH:-}" || -z "${APPLE_API_KEY_ID:-}" || -z "${APPLE_API_ISSUER_ID:-}" ]]; then
    echo "==> Notarization credentials not set: skipping notarization"
    return 0
  fi
  if [[ -z "$IDENTITY" ]]; then
    echo "warning: notarization needs a Developer ID signed build (MACOS_SIGN_IDENTITY); skipping" >&2
    return 0
  fi
  echo "==> Notarizing $DMG"
  local out status id
  out="$(xcrun notarytool submit "$DMG" --key "$APPLE_API_KEY_PATH" --key-id "$APPLE_API_KEY_ID" \
    --issuer "$APPLE_API_ISSUER_ID" --wait --output-format json)"
  echo "$out"
  status="$(plutil -extract status raw -o - - <<<"$out" 2>/dev/null || true)"
  if [[ "$status" != "Accepted" ]]; then
    id="$(plutil -extract id raw -o - - <<<"$out" 2>/dev/null || true)"
    if [[ -n "$id" ]]; then
      xcrun notarytool log "$id" --key "$APPLE_API_KEY_PATH" --key-id "$APPLE_API_KEY_ID" \
        --issuer "$APPLE_API_ISSUER_ID" || true
    fi
    echo "error: notarization status: ${status:-unknown}" >&2
    exit 1
  fi
  xcrun stapler staple "$DMG"
  xcrun stapler validate "$DMG"
}

case "${1:-}" in
  sign) cmd_sign ;;
  smoke) cmd_smoke ;;
  dmg) cmd_dmg ;;
  notarize) cmd_notarize ;;
  all) cmd_sign; cmd_smoke; cmd_dmg; cmd_notarize ;;
  *) sed -n '2,20p' "$0"; exit 2 ;;
esac
