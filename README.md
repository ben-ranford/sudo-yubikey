# sudo-yubikey

YubiKey authentication for sudo on macOS, with native Touch ID and password fallback.

## Install the command

```sh
brew install ben-ranford/tap/sudo-yubikey
sudo-yubikey --version
sudo-yubikey --help
```

Installation only adds the command and dependencies. It does not change PAM, enroll
keys, or install a background job. Running without arguments shows help.

## Authentication policy

A mapped key can authenticate sudo before native Touch ID and password methods.
An absent, incorrect or unsuccessful key falls through to those existing methods.
There is no mandatory-key mode. This is an alternative authentication method,
not password-plus-key two-factor authentication.

The generated rule requires user presence (touch). By default it explicitly turns
off PIN and biometric verification. `--pin` requests PIN verification and requires
a compatible FIDO2 key and enrollment. `cue` displays the touch reminder.
The module never receives `nouserok` or `alwaysok`.

A cached sudo timestamp can authorize later commands without invoking PAM. This
tool does not change sudoers or timestamp policy and does not promise a touch for
every command.

## Configure deliberately

Configuration targets macOS 14 or later with the native `sudo_local` include and
password fallback. Custom authentication stacks, earlier macOS versions, and
legacy boot daemons are refused. No physical hardware authentication tests have
been performed for this release; only automated logic tests have been run.
Apple Silicon and Intel hardware behavior is not verified.

1. Enroll the invoking user using Yubico's `pamu2fcfg` procedure before activation.
   Keep `/etc/u2f_mappings` root-owned, a regular file, and not writable by other
   users. Enroll a backup key. Do not share this file or put it in Git.
   Enrollment and PIN setup are intentionally outside this command.
2. Keep a separate administrator recovery shell open while changing PAM.
3. Find the module path, normally
   `$(brew --prefix pam-u2f)/lib/pam/pam_u2f.so`.
4. Review a dry run, then explicitly activate the same plan:

```sh
sudo-yubikey --install --dry-run --module /root-controlled/path/pam_u2f.so
sudo /absolute/path/to/sudo-yubikey --install --module /root-controlled/path/pam_u2f.so
```

The default refuses module paths or ancestors that are user-owned, writable by
others, or symlinks after resolving the module path. It also refuses non-system
dynamic-library dependencies pending administrator review. Homebrew normally
uses a user-owned prefix; its module therefore needs an explicit trust decision.
If you accept that anyone able to replace that module or its dependent libraries
can execute code in sudo's root context, the opt-in form is:

```sh
module="$(brew --prefix pam-u2f)/lib/pam/pam_u2f.so"
sudo-yubikey --install --dry-run --module "$module" --trust-homebrew-module
sudo "$(command -v sudo-yubikey)" --install --module "$module" --trust-homebrew-module
```

The flag does not make Homebrew's files root-controlled. For a stronger boundary,
have an administrator provision and audit the module and its entire dependency
chain outside user-writable paths. As with any administrator command, review and
trust the executable and interpreter before running them as root.

Use matching origin/appid and PIN policy during enrollment and authentication;
see [Yubico's instructions](https://developers.yubico.com/pam-u2f/). Do not alter
these credential parameters casually. This command leaves origin/appid at the
module defaults; hostname changes can invalidate that enrollment.

After activation, test a fresh sudo authentication from a second terminal with
`sudo -k`, both with and without the key, while retaining the recovery shell.
Do not close that shell until fallback succeeds. Hardware verification is the
administrator's responsibility.

## Status, removal and recovery

```sh
sudo-yubikey --status
sudo-yubikey --disable --dry-run
sudo /absolute/path/to/sudo-yubikey --disable
```

Removal deletes only recognized rules using `/etc/u2f_mappings` and the tool's
markers. It preserves unrelated PAM content and enrolled mappings. Unknown U2F
rules require manual review. No launch daemon is installed or supported.

Every change gets a unique root-only backup under `/var/db/sudo-yubikey`, with a
manifest identifying each target, its previous permission mode and its backup
file. Writes use same-directory atomic replacement; a failed write rolls all
targets back. There is no guarantee across power loss between multiple file
replacements. A recovery administrator can use the manifest to restore the
previous files and modes; a target recorded as `null` did not exist before the
change. Keep the recovery shell available for this operation.

Installation is idempotent. It refuses unknown PAM layouts rather than guessing,
and never deletes the whole `sudo_local` file or rewrites configuration at boot.

## Development

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile sudo_yubikey.py
bash -n sudo-yubikey.sh
shellcheck sudo-yubikey.sh
```

Tests use temporary fixtures and mocks, not the host PAM stack, sudo authentication
or physical hardware. CI runs the suite on Linux and macOS.

## License and attribution

[EPL-2.0](LICENSE.md). The original implementation was based on
[Arthur Ginzburg's sudo-touchid](https://github.com/artginzburg/sudo-touchid).
Authentication uses [Yubico pam-u2f](https://developers.yubico.com/pam-u2f/).
