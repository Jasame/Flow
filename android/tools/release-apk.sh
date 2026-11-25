#!/bin/sh
# The APKs to hand out, signed with the owner's key. The key and its password stay on the owner's Mac:
#   ~/.flow-android/flow-release.jks (alias flow), its password in the macOS keychain (service flow-android-release)
# (or FLOW_KEYSTORE / FLOW_KS_PW in the environment). Gradle never sees the password.
#
#   tools/release-apk.sh [beta|prod|both]      → android/dist/flow-beta-<version>.apk, flow-<version>.apk
#
# Raise flow.versionCode in gradle.properties before handing out a new one.
set -eu
cd "$(dirname "$0")/.."
which=${1:-both}
case "$which" in
  beta) flavors="beta" ;; prod) flavors="prod" ;; both) flavors="beta prod" ;;
  *) echo "usage: tools/release-apk.sh [beta|prod|both]" >&2; exit 2 ;;
esac
KS=${FLOW_KEYSTORE:-$HOME/.flow-android/flow-release.jks}
[ -f "$KS" ] || { echo "no keystore at $KS (android/README.md, 「签名」)" >&2; exit 1; }
SDK=${ANDROID_HOME:-$(sed -n 's/^sdk.dir=//p' local.properties 2>/dev/null)}
BT=$(ls -d "$SDK"/build-tools/* | sort -V | tail -1)
ver=$(sed -n 's/^flow.versionName=//p' gradle.properties)

tasks=""
for f in $flavors; do tasks="$tasks assemble$(printf %s "$f" | cut -c1 | tr a-z A-Z)$(printf %s "$f" | cut -c2-)Release"; done
./gradlew -q $tasks

if [ -z "${FLOW_KS_PW:-}" ]; then
  FLOW_KS_PW=$(security find-generic-password -a flow-android -s flow-android-release -w) || { echo "the keystore password is not in the keychain" >&2; exit 1; }
fi
export FLOW_KS_PW
mkdir -p dist
for f in $flavors; do
  in=app/build/outputs/apk/$f/release/app-$f-release-unsigned.apk
  if [ "$f" = beta ]; then out=dist/flow-beta-$ver.apk; else out=dist/flow-$ver.apk; fi
  "$BT/zipalign" -f -p 4 "$in" dist/.aligned.apk
  "$BT/apksigner" sign --ks "$KS" --ks-key-alias flow --ks-pass env:FLOW_KS_PW --key-pass env:FLOW_KS_PW --out "$out" dist/.aligned.apk
  rm -f dist/.aligned.apk "$out.idsig"
  "$BT/apksigner" verify "$out"
  echo "$out  $(du -h "$out" | cut -f1)  sha256 $(shasum -a 256 "$out" | cut -c1-16)…"
done
unset FLOW_KS_PW
