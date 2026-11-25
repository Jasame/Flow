#!/bin/sh
# Signed APKs, each flavor with its own key (the user's choice, 2026-11-25):
#   beta (语流内测): ~/.flow-android/flow-beta.jks, password in the macOS keychain (service flow-android-beta).
#         A copy of both is in the repository's Actions secrets (FLOW_BETA_KEYSTORE, FLOW_BETA_KS_PW): every push to main
#         makes a signed beta APK there (.github/workflows/android.yml), each one installs over the one before.
#   prod (语流):    ~/.flow-android/flow-release.jks, password in the keychain (service flow-android-release). It never
#         leaves the owner's Mac.
# Both alias `flow`. Instead of the keychain: FLOW_BETA_KEYSTORE_FILE / FLOW_BETA_KS_PW and FLOW_KEYSTORE / FLOW_KS_PW.
# Gradle never sees a password.
#
#   tools/release-apk.sh [beta|prod|both]      → android/dist/flow-beta-<version>.apk, flow-<version>.apk
#
# versionCode: flow.versionCode in gradle.properties (raise it before handing out a prod APK), or FLOW_VERSION_CODE
# (CI: 100 + the run number, so every beta from main is newer than the one before).
set -eu
cd "$(dirname "$0")/.."
which=${1:-both}
case "$which" in
  beta) flavors="beta" ;; prod) flavors="prod" ;; both) flavors="beta prod" ;;
  *) echo "usage: tools/release-apk.sh [beta|prod|both]" >&2; exit 2 ;;
esac
SDK=${ANDROID_HOME:-$(sed -n 's/^sdk.dir=//p' local.properties 2>/dev/null)}
BT=$(ls -d "$SDK"/build-tools/* | sort -V | tail -1)
ver=$(sed -n 's/^flow.versionName=//p' gradle.properties)

# the key file and its password for one flavor
keyfile() { if [ "$1" = beta ]; then echo "${FLOW_BETA_KEYSTORE_FILE:-$HOME/.flow-android/flow-beta.jks}"; else echo "${FLOW_KEYSTORE:-$HOME/.flow-android/flow-release.jks}"; fi; }
password() {
  if [ "$1" = beta ] && [ -n "${FLOW_BETA_KS_PW:-}" ]; then printf %s "$FLOW_BETA_KS_PW"; return; fi
  if [ "$1" = prod ] && [ -n "${FLOW_KS_PW:-}" ]; then printf %s "$FLOW_KS_PW"; return; fi
  if [ "$1" = beta ]; then service=flow-android-beta; else service=flow-android-release; fi
  security find-generic-password -a flow-android -s "$service" -w 2>/dev/null || { echo "no password for the $1 key (keychain $service)" >&2; exit 1; }
}
for f in $flavors; do [ -f "$(keyfile "$f")" ] || { echo "no $f keystore at $(keyfile "$f") (android/README.md, 「发 APK」)" >&2; exit 1; }; done

tasks=""
for f in $flavors; do tasks="$tasks assemble$(printf %s "$f" | cut -c1 | tr a-z A-Z)$(printf %s "$f" | cut -c2-)Release"; done
./gradlew -q $tasks

mkdir -p dist
sum() { if command -v shasum >/dev/null; then shasum -a 256 "$1"; else sha256sum "$1"; fi; }
for f in $flavors; do
  in=app/build/outputs/apk/$f/release/app-$f-release-unsigned.apk
  if [ "$f" = beta ]; then out=dist/flow-beta-$ver.apk; else out=dist/flow-$ver.apk; fi
  "$BT/zipalign" -f -p 4 "$in" dist/.aligned.apk
  FLOW_SIGN_PW=$(password "$f"); export FLOW_SIGN_PW
  "$BT/apksigner" sign --ks "$(keyfile "$f")" --ks-key-alias flow --ks-pass env:FLOW_SIGN_PW --key-pass env:FLOW_SIGN_PW --out "$out" dist/.aligned.apk
  unset FLOW_SIGN_PW
  rm -f dist/.aligned.apk "$out.idsig"
  "$BT/apksigner" verify "$out"
  echo "$out  $(du -h "$out" | cut -f1)  sha256 $(sum "$out" | cut -c1-16)…"
done
