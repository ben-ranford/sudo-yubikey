# sudo-yubikey

Use a YubiKey to authenticate `sudo` on macOS, with the existing Touch ID and
password methods available if the key is absent or authentication fails.
Successful key authentication is enough to authorise sudo, while cached sudo
authorisation can let commands run without another key touch.

## Install

On macOS 14 or later, install the command and its Python and pam-u2f dependencies
with [Homebrew](https://brew.sh), then configure a FIDO U2F or FIDO2 YubiKey using
the steps below.

```sh
brew install ben-ranford/tap/sudo-yubikey
sudo-yubikey --version
```

## Configure

Keep a separate administrator shell open while you configure and test
authentication so you can recover if a PAM change prevents sudo access.

### Enrol your keys

Follow [Yubico's pamu2fcfg instructions](https://developers.yubico.com/pam-u2f/#obtaining-key-handles-and-public-keys)
to enrol your main and backup keys with the default origin and appid, then place
both credentials on one line for your username in `/etc/u2f_mappings`. Use a
regular, root-owned file without group or other write permission.

### Enable authentication

| Homebrew module | Separately provisioned module |
| --- | --- |
| Use `$(brew --prefix pam-u2f)/lib/pam/pam_u2f.so`. | Use the absolute path to your `pam_u2f.so`. |
| Homebrew normally uses a user-owned prefix, so anyone who can replace the module or its libraries can execute code as root. | The command requires a root-controlled module path and accepts only dependencies in `/usr/lib/` or `/System/Library/`. |
| Pass `--trust-homebrew-module` to accept this access. | Omit `--trust-homebrew-module` to enforce these checks. |

Both options retain the PAM-file and mapping-file checks described in
[SECURITY.md](SECURITY.md).

For the Homebrew module, review the dry-run output before running the install command:

```sh
module="$(brew --prefix pam-u2f)/lib/pam/pam_u2f.so"
sudo "$(command -v sudo-yubikey)" --install --dry-run --module "$module" --trust-homebrew-module
sudo "$(command -v sudo-yubikey)" --install --module "$module" --trust-homebrew-module
```

For a separately provisioned module, replace the example path and review the
dry-run output before running the install command:

```sh
module="/root-controlled/path/pam_u2f.so"
sudo "$(command -v sudo-yubikey)" --install --dry-run --module "$module"
sudo "$(command -v sudo-yubikey)" --install --module "$module"
```

For touch and PIN, configure a PIN and matching FIDO2 credentials, then add
`--pin` to the preview and install commands.

### Test authentication

In a second terminal, clear the sudo timestamp and request fresh authentication:

```sh
sudo -k
sudo -v
```

Touch the enrolled key when prompted, then repeat both commands with your backup
key and again with no key connected to check the existing fallback. Keep the
administrator shell open until all three checks succeed.

## Check or disable

To inspect the current sudo PAM files, run:

```sh
sudo-yubikey --status
```

To remove the recognised YubiKey rules, preview the change before applying it:

```sh
sudo-yubikey --disable --dry-run
sudo "$(command -v sudo-yubikey)" --disable
```

Disabling preserves the other PAM settings and leaves `sudo_local` and the key
mappings in place.

## Configuration notes and recovery

The default origin and appid depend on the hostname, so a hostname change can
require you to enrol again. The default authentication policy disables PIN and
biometric verification; `--pin` enables PIN verification for compatible
credentials.

If installation rejects a mapping, check that `/etc/u2f_mappings` is a regular,
root-owned file with no group or other write permission and exactly one line
for the invoking user. Keep this file private and do not replace it with a
symbolic link.

The command rejects unfamiliar PAM authentication layouts and refuses changes
while a legacy sudo-yubikey boot daemon is present. Review either condition
before changing the configuration.

## Licence

Licensed under [EPL-2.0](LICENSE.md), with authentication provided by
[Yubico pam-u2f](https://developers.yubico.com/pam-u2f/). The original
implementation was based on [Arthur Ginzburg's sudo-touchid](https://github.com/artginzburg/sudo-touchid).
