# ZCAMS Local Runner

This workspace contains the ZCAMS migration project for ZAFFA Clearing &
Forwarding.

The app you should run locally is:

```text
cfa-dash/
```

`cfa-backend/` and `cfa-frontend/` are reference projects from the original
Django + React system. The active working app is the Plotly Dash rewrite in
`cfa-dash/`.

## Quick Start On Windows

From the workspace root:

```powershell
.\run-zcams.ps1
```

Then open:

```text
http://127.0.0.1:8050/
```

If PowerShell blocks scripts on your machine, double-click or run:

```bat
run-zcams.bat
```

The launcher will:

1. Move into `cfa-dash/`.
2. Create `.venv/` if it does not exist.
3. Install `requirements.txt`.
4. Copy `.env.example` to `.env` if `.env` is missing.
5. Start the Dash app.

## Test

```powershell
.\test-zcams.ps1
```

This uses a workspace-local pytest temp directory to avoid Windows `%TEMP%`
permission issues.

## Requirements

- Windows 10/11
- Python 3.11 or newer
- Internet connection the first time dependencies are installed

## Project Roles

| Folder | Role |
| --- | --- |
| `cfa-dash/` | Active Dash app to run and build |
| `cfa-backend/` | Django/DRF reference backend |
| `cfa-frontend/` | React/Vite reference frontend |

## Branding

- System: ZCAMS
- Company / tenant: ZAFFA Clearing & Forwarding
- Theme: Zambian national flag palette
