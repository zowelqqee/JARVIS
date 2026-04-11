#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VENV_PYTHON="${REPO_ROOT}/.venv-desktop-packaging/bin/python"
DEPLOY_BIN="${REPO_ROOT}/.venv-desktop-packaging/bin/pyside6-deploy"
SPEC_FILE="${REPO_ROOT}/packaging/macos/pysidedeploy.spec"
BUILD_DIR="${REPO_ROOT}/dist/macos_build"
FINAL_APP_PATH="${BUILD_DIR}/JARVIS.app"
DMG_STAGE_DIR="${BUILD_DIR}/dmg_stage"
DMG_PATH="${BUILD_DIR}/JARVIS.dmg"
PACKAGING_HOME="${REPO_ROOT}/tmp/runtime/macos_packaging_home"
XDG_CACHE_HOME="${PACKAGING_HOME}/.cache"
PIP_CACHE_DIR="${XDG_CACHE_HOME}/pip"
APP_INFO_PLIST="${FINAL_APP_PATH}/Contents/Info.plist"
APP_MACOS_DIR="${FINAL_APP_PATH}/Contents/MacOS"

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "Missing build virtualenv python at ${VENV_PYTHON}" >&2
  exit 1
fi

if [[ ! -x "${DEPLOY_BIN}" ]]; then
  echo "Missing pyside6-deploy at ${DEPLOY_BIN}" >&2
  exit 1
fi

if [[ ! -f "${SPEC_FILE}" ]]; then
  echo "Missing deploy spec at ${SPEC_FILE}" >&2
  exit 1
fi

cd "${REPO_ROOT}"

rm -rf "${FINAL_APP_PATH}" "${DMG_STAGE_DIR}" "${DMG_PATH}" "${PACKAGING_HOME}"
mkdir -p "${BUILD_DIR}"
mkdir -p "${PIP_CACHE_DIR}"

export HOME="${PACKAGING_HOME}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR}"

"${DEPLOY_BIN}" -c "${SPEC_FILE}" -f

if [[ ! -d "${FINAL_APP_PATH}" ]]; then
  echo "Build completed but ${FINAL_APP_PATH} was not created" >&2
  exit 1
fi

APP_EXECUTABLE_NAME="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "${APP_INFO_PLIST}" 2>/dev/null || printf 'main')"
if [[ -x "${APP_MACOS_DIR}/${APP_EXECUTABLE_NAME}" && "${APP_EXECUTABLE_NAME}" != "JARVIS" ]]; then
  mv "${APP_MACOS_DIR}/${APP_EXECUTABLE_NAME}" "${APP_MACOS_DIR}/JARVIS"
  /usr/libexec/PlistBuddy -c "Set :CFBundleExecutable JARVIS" "${APP_INFO_PLIST}"
fi

/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName JARVIS" "${APP_INFO_PLIST}" || /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string JARVIS" "${APP_INFO_PLIST}"
/usr/libexec/PlistBuddy -c "Set :CFBundleName JARVIS" "${APP_INFO_PLIST}" || /usr/libexec/PlistBuddy -c "Add :CFBundleName string JARVIS" "${APP_INFO_PLIST}"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.jarvis.desktop" "${APP_INFO_PLIST}" || /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string com.jarvis.desktop" "${APP_INFO_PLIST}"

if [[ ! -x "${APP_MACOS_DIR}/JARVIS" ]]; then
  echo "Build completed but ${FINAL_APP_PATH} does not contain an executable app binary" >&2
  exit 1
fi

codesign --force --deep --sign - "${FINAL_APP_PATH}"

mkdir -p "${DMG_STAGE_DIR}"
cp -R "${FINAL_APP_PATH}" "${DMG_STAGE_DIR}/"
ln -s /Applications "${DMG_STAGE_DIR}/Applications"

hdiutil create \
  -volname "JARVIS" \
  -srcfolder "${DMG_STAGE_DIR}" \
  -ov \
  -format UDZO \
  "${DMG_PATH}"

echo "Built app: ${FINAL_APP_PATH}"
echo "Built dmg: ${DMG_PATH}"
