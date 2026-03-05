# Building the Controller Config GUI Executable

Packages the controller configuration tool as a standalone executable
that runs without a Python installation.

## Quick Build (Windows)

```bash
make gui-exe
```

The built executable appears at `dist/raptacon-controls-editor.exe`.

## Manual Build

```bash
pip install pyinstaller
pip install -r host/requirements.txt

# Generate icon (first time or after logo change)
python host/make_ico.py

# Build
cd host
pyinstaller controller_config_win.spec --distpath ../dist --workpath ../build/gui --clean -y
```

## Platform Spec Files

| Platform | Spec file | Status |
|----------|-----------|--------|
| Windows  | `host/controller_config_win.spec` | Active |
| macOS    | `host/controller_config_mac.spec` | Planned |
| Linux    | `host/controller_config_linux.spec` | Planned |

## CI/CD

The GitHub Actions workflow `.github/workflows/gui_release.yml` automatically
builds and uploads the executable when a GitHub Release is published.

Use **Actions > Build Controller Config GUI > Run workflow** to trigger
a test build manually (the artifact is downloadable from the workflow run).

## Code Signing

### Current: Self-signed certificate

The CI workflow signs the EXE if the `CODE_SIGN_CERT` and `CODE_SIGN_PASSWORD`
GitHub secrets are configured. The signing step is skipped when secrets are
not set.

#### Setting up the self-signed certificate (one-time)

Run in PowerShell as administrator:

```powershell
# 1. Generate a code signing certificate (3-year validity)
$cert = New-SelfSignedCertificate -Type CodeSigningCert `
    -Subject "CN=Raptacon FRC 3200, O=Raptacon" `
    -FriendlyName "Raptacon Code Signing" `
    -CertStoreLocation Cert:\CurrentUser\My `
    -NotAfter (Get-Date).AddYears(3)

# 2. Export as PFX (enter a strong password when prompted)
$pw = Read-Host "Enter PFX password" -AsSecureString
Export-PfxCertificate -Cert $cert -FilePath raptacon_codesign.pfx -Password $pw

# 3. Base64-encode (copies to clipboard)
[Convert]::ToBase64String([IO.File]::ReadAllBytes("raptacon_codesign.pfx")) | Set-Clipboard
```

Then in GitHub (Settings > Secrets and variables > Actions):
- Add `CODE_SIGN_CERT` — paste the base64 string
- Add `CODE_SIGN_PASSWORD` — the password from step 2

Delete the local PFX file after uploading:
```powershell
Remove-Item raptacon_codesign.pfx
```

### Windows SmartScreen

Windows SmartScreen uses reputation-based trust. Self-signed and newly-signed
executables will show a warning:

> **Windows protected your PC** — Microsoft Defender SmartScreen prevented
> an unrecognized app from starting.

To run: click **More info**, then **Run anyway**.

### Future: SignPath Foundation

The project qualifies for free EV code signing through
[SignPath Foundation](https://signpath.org/foundation) (MIT license, open source).
EV certificates provide immediate SmartScreen trust. See the CLAUDE.md TODO
for tracking this upgrade.
