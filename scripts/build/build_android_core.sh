#!/usr/bin/env bash
# Cross-compile the Android arm64 Rust core (librustdesk.so) from a tagged
# worktree. Runs in WSL; the Windows-side APK packaging is build_apk.ps1.
#
# usage: build_android_core.sh [CLIENT_DIR]
#   CLIENT_DIR  client source inside a tag worktree, default
#               /mnt/d/RD/build/src-1.5.1.2/client
set -euo pipefail

CLIENT_DIR=${1:-/mnt/d/RD/build/src-1.5.1.2/client}
BUILD_ROOT=${BUILD_ROOT:-/opt/build}
DST="$BUILD_ROOT/rustdesk-android-$(basename "$(dirname "$CLIENT_DIR")")"
LOG="$BUILD_ROOT/android-core.log"

export ANDROID_NDK_HOME=${ANDROID_NDK_HOME:-/opt/android/android-ndk-r28c}
export ANDROID_NDK_ROOT="$ANDROID_NDK_HOME"
export CARGO_HOME=${CARGO_HOME:-/opt/rust/cargo}
export RUSTUP_HOME=${RUSTUP_HOME:-/opt/rust/rustup}
export PATH="$CARGO_HOME/bin:$PATH"
export CARGO_TARGET_DIR="$DST/target"
NDK_SYSROOT="$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/sysroot"
BINDGEN_ARGS="--target=aarch64-linux-android21 --sysroot=$NDK_SYSROOT"

mkdir -p "$BUILD_ROOT"
exec > >(tee "$LOG") 2>&1

echo "== source =="
echo "CLIENT_DIR=$CLIENT_DIR"
[ -f "$CLIENT_DIR/Cargo.toml" ] || { echo "not a client tree: $CLIENT_DIR"; exit 1; }

echo "== rustup target =="
rustup target add aarch64-linux-android

echo "== rsync to $DST =="
mkdir -p "$DST"
rsync -a --delete \
  --exclude=.git --exclude=target --exclude=build --exclude=.dart_tool \
  --exclude=local.properties --exclude=jniLibs --exclude=.gradle \
  "$CLIENT_DIR"/ "$DST"/
mkdir -p "$DST/.cargo"
[ -f "$BUILD_ROOT/rustdesk/.cargo/config.toml" ] && cp "$BUILD_ROOT/rustdesk/.cargo/config.toml" "$DST/.cargo/config.toml"
cd "$DST"

echo "== cargo ndk build =="
env "BINDGEN_EXTRA_CLANG_ARGS_aarch64-linux-android=$BINDGEN_ARGS" \
  cargo ndk --platform 21 --target aarch64-linux-android build \
  --release --features flutter,hwcodec --lib

OUT_SO="$CARGO_TARGET_DIR/aarch64-linux-android/release/liblibrustdesk.so"
DEST_DIR="$CLIENT_DIR/flutter/android/app/src/main/jniLibs/arm64-v8a"
mkdir -p "$DEST_DIR"
cp "$OUT_SO" "$DEST_DIR/librustdesk.so"
"$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip" "$DEST_DIR/librustdesk.so"
ls -la "$DEST_DIR"
echo ANDROID_CORE_READY
