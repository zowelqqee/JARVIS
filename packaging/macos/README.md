# macOS Packaging

This directory contains the reproducible packaging setup for building the
desktop app as a macOS `.app` bundle and wrapping it in a `.dmg`.

## Expected environment

- macOS with Xcode Command Line Tools installed
- Python 3.13
- A local build virtualenv at `.venv-desktop-packaging`

## Build dependencies

Install the packaging dependencies into the local build virtualenv:

```bash
python3 -m venv .venv-desktop-packaging
./.venv-desktop-packaging/bin/python -m pip install -r packaging/macos/requirements-build.txt
```

## Build

From the repo root:

```bash
packaging/macos/build_dmg.sh
```

Outputs:

- `.app`: `dist/macos_build/JARVIS.app`
- `.dmg`: `dist/macos_build/JARVIS.dmg`

The build includes the `docs/` directory inside the app bundle so grounded QA
continues to resolve product documentation at runtime.

The build script also redirects `HOME` and cache directories into repo-local
`tmp/runtime/` paths so `Nuitka` can compile successfully inside a restricted
workspace environment.
