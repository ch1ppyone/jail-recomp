#!/usr/bin/env bash
# Shared Android environment for the scripts in this folder. Source it; do not execute it.
# shellcheck shell=bash

ANDROID_SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}}"
ANDROID_NDK="${ANDROID_NDK_HOME:-$ANDROID_SDK/ndk/28.2.13676358}"
if [ -x "$ANDROID_SDK/cmake/3.31.6/bin/cmake" ]; then
    ANDROID_CMAKE="$ANDROID_SDK/cmake/3.31.6/bin/cmake"
else
    ANDROID_CMAKE="${CMAKE:-cmake}"
fi
ANDROID_ADB="$ANDROID_SDK/platform-tools/adb"

if [ -z "${JAVA_HOME:-}" ] && [ -d /opt/homebrew/opt/openjdk@17 ]; then
    JAVA_HOME=/opt/homebrew/opt/openjdk@17
fi

export ANDROID_HOME="$ANDROID_SDK"
export ANDROID_SDK_ROOT="$ANDROID_SDK"
export ANDROID_NDK_HOME="$ANDROID_NDK"
export JAVA_HOME
