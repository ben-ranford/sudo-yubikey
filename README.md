# sudo-yubikey

Authenticate sudo on macOS with a YubiKey, while keeping native Touch ID and
password fallback. The command configures PAM explicitly, preserves unrelated
settings, and backs up changes before writing.

## Installation

Requires macOS 14 or later and [Homebrew](https://brew.sh).

```sh
brew install ben-ranford/tap/sudo-yubikey
sudo-yubikey --version
sudo-yubikey --help
```

This installs the command and its dependencies. It does not activate PAM, enroll
keys, or install a background job. Running without arguments shows help.

## Usage

```sh
sudo-yubikey --status             # Show the current sudo PAM configuration
sudo-yubikey --disable --dry-run  # Preview removal of recognized YubiKey rules
sudo "$(command -v sudo-yubikey)" --disable
```

A mapped key can authenticate before Touch ID or password. An absent, incorrect
or unsuccessful key falls through to those existing methods. This is an
alternative authentication method, not a mandatory key or password-plus-key
second factor. Cached sudo authorization can skip PAM; a touch is not required
for every command.

## Configuration

1. Enroll the invoking user and a backup key using
   [Yubico's `pamu2fcfg` instructions](https://developers.yubico.com/pam-u2f/).
   Keep `/etc/u2f_mappings` root-owned, a regular file, and not writable by other
   users. Enrollment and PIN setup are separate from this command.
2. Keep an administrator recovery shell open while changing PAM.
3. Choose a trusted `pam_u2f.so` module and review a dry run before activation.

For a module and dependency chain provisioned in root-controlled locations:

```sh
sudo-yubikey --install --dry-run --module /root-controlled/path/pam_u2f.so
sudo "$(command -v sudo-yubikey)" --install --module /root-controlled/path/pam_u2f.so
```

Homebrew normally uses a user-owned prefix. To accept that its module and
libraries execute in sudo's root context, explicitly opt in:

```sh
module="$(brew --prefix pam-u2f)/lib/pam/pam_u2f.so"
sudo-yubikey --install --dry-run --module "$module" --trust-homebrew-module
sudo "$(command -v sudo-yubikey)" --install --module "$module" --trust-homebrew-module
```

Anyone able to replace those libraries can execute code as root. The trust flag
does not change their ownership or relax PAM-file checks. Review and trust the
command and interpreter before running them as root; see the [security model](SECURITY.md).

| Option | Behavior |
| --- | --- |
| `--install` | Activate a recognized macOS PAM layout; requires `--module` and enrollment. |
| `--dry-run` | Preview an installation or removal without writes. |
| `--pin` | Request PIN verification with a compatible FIDO2 key and enrollment. |
| `--trust-homebrew-module` | Explicitly accept a user-managed module and its libraries. |
| `--disable` | Remove recognized rules, preserving other settings and mappings. |
| `--status` | Display the current sudo PAM files. |

The default requests touch and turns off PIN and biometric verification. Use
matching origin/appid and PIN policy during enrollment and authentication.
Origin/appid remain at the module defaults, so hostname changes can invalidate
enrollment. No `nouserok` or `alwaysok` option is generated.

After activation, use `sudo -k` in a second terminal to check fresh authentication
with and without the key. Keep the recovery shell open until fallback succeeds.

## Troubleshooting

- **Module trust rejected:** provision and audit the module and all dependencies
  in root-controlled paths, or deliberately accept the Homebrew trust option.
- **Enrollment rejected:** check the invoking user's mapping, ownership and
  permissions. Do not publish mappings or credentials.
- **Custom PAM layout or legacy daemon detected:** review it manually. The tool
  refuses unfamiliar authentication stacks rather than bypassing existing factors.
- **A write fails:** previous files are rolled back. Unique root-only backups in
  `/var/db/sudo-yubikey` contain a manifest of targets, previous modes and backup
  files. Keep the recovery shell available; multi-file changes are not atomic
  across power loss.

Repeated installation is idempotent. Removal does not delete `sudo_local`, erase
mappings, or install a job that rewrites configuration at boot.

## Development and contributing

```sh
git clone https://github.com/ben-ranford/sudo-yubikey.git
cd sudo-yubikey
python3 -m unittest discover -s tests -v
python3 -m py_compile sudo_yubikey.py
bash -n sudo-yubikey.sh
shellcheck sudo-yubikey.sh
```

The test suite covers configuration, CLI preflight and failure handling with
temporary fixtures and mocks. CI runs on Linux and macOS. Open an
[issue](https://github.com/ben-ranford/sudo-yubikey/issues) or submit a pull request
with focused changes and relevant tests. See [release changes](CHANGELOG.md).

## License and attribution

Licensed under [EPL-2.0](LICENSE.md). The original implementation was based on
[Arthur Ginzburg's sudo-touchid](https://github.com/artginzburg/sudo-touchid).
Authentication uses [Yubico pam-u2f](https://developers.yubico.com/pam-u2f/).
