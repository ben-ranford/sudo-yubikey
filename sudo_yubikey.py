#!/usr/bin/env python3
"""Explicit, transactional macOS sudo PAM configuration. EPL-2.0."""
import argparse
import contextlib
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import uuid

VERSION = '2.0.0'
MARKER = '# sudo-yubikey managed authentication (password/Touch ID fallback)\n'
RULE = re.compile(r'^\s*auth\s+sufficient\s+\S*\bpam_u2f\.so\s+authfile=/etc/u2f_mappings(?:\s+\S+)*\s*$')
LEGACY_MARKER = '# YubiKey U2F authentication (primary)'

class Unsafe(ValueError):
    pass


def secure(path, directory=False):
    """Require a root-controlled, nonsymlink path, including all ancestors."""
    path = Path(path)
    for item in (path, *path.parents):
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise Unsafe(f'Not root-controlled: {item}')
        expected_dir = directory or item != path
        if not (stat.S_ISDIR(info.st_mode) if expected_dir else stat.S_ISREG(info.st_mode)):
            raise Unsafe(f'Unexpected file type: {item}')


def clean(text):
    kept = []
    for line in text.splitlines(keepends=True):
        if 'pam_u2f.so' in line and not line.lstrip().startswith('#'):
            if not RULE.match(line.rstrip('\n')):
                raise Unsafe('Unrecognized existing pam_u2f rule; review manually')
            continue
        if line == MARKER or line.strip() == LEGACY_MARKER:
            continue
        kept.append(line)
    return ''.join(kept)


def render(main, local, module=None, pin=False):
    main_clean, local_clean = clean(main), clean(local)
    if module is not None:
        if not re.fullmatch(r'/[A-Za-z0-9_./+-]+', str(module)):
            raise Unsafe('Module path must be absolute and contain no PAM whitespace')
        includes = list(re.finditer(r'^auth\s+include\s+sudo_local\s*$', main_clean, re.M))
        if len(includes) != 1:
            raise Unsafe('Expected exactly one sudo_local include; unsupported PAM layout')
        if any(re.match(r'^\s*auth\s+', line) for line in main_clean[:includes[0].start()].splitlines()):
            raise Unsafe('Authentication before sudo_local; review manually')
        allowed_main = re.compile(r'^auth\s+(?:include\s+sudo_local|sufficient\s+pam_smartcard\.so|required\s+pam_opendirectory\.so)\s*$')
        for line in main_clean.splitlines():
            if re.match(r'^\s*auth\s+', line) and not allowed_main.fullmatch(line):
                raise Unsafe('Custom authentication in sudo; review manually')
        for line in local_clean.splitlines():
            if line.strip() and not line.lstrip().startswith('#') and not re.fullmatch(r'auth\s+sufficient\s+pam_tid\.so\s*', line):
                raise Unsafe('Custom sudo_local rules; review manually')
        if len(re.findall(r'^auth\s+required\s+pam_opendirectory\.so\s*$', main_clean, re.M)) != 1:
            raise Unsafe('Native password fallback missing or duplicated; unsupported PAM layout')
        policy = 'pinverification=1' if pin else 'pinverification=0 userverification=0'
        local_clean = (MARKER + f'auth sufficient {module} authfile=/etc/u2f_mappings '
                       f'cue userpresence=1 {policy}\n' + local_clean)
    return main_clean, local_clean


def atomic(path, data, mode=0o644):
    fd, name = tempfile.mkstemp(prefix='.sudo-yubikey-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        dfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def transaction(changes, backups, writer=atomic):
    """Back up every target before writes; restore all targets if any write fails."""
    if not changes:
        return None
    originals = {p: (p.read_bytes(), stat.S_IMODE(p.stat().st_mode)) if p.exists() else None
                 for p in changes}
    folder = backups / (datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                        + '-' + uuid.uuid4().hex)
    folder.mkdir(mode=0o700)
    manifest = {}
    for index, (p, original) in enumerate(originals.items()):
        filename = str(index)
        manifest[str(p)] = {'file': filename, 'mode': original[1]} if original else None
        if original:
            (folder / filename).write_bytes(original[0])
            (folder / filename).chmod(0o600)
    (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    try:
        for p, data in changes.items():
            writer(p, data, originals[p][1] if originals[p] else 0o644)
    except BaseException:
        failures = []
        for p, original in originals.items():
            try:
                if original:
                    atomic(p, original[0], original[1])
                elif p.exists():
                    p.unlink()
            except OSError:
                failures.append(str(p))
        if failures:
            raise Unsafe(f'Rollback incomplete: {failures}; recovery backup: {folder}') from None
        raise
    return folder


@contextlib.contextmanager
def locked(backups):
    secure(backups, directory=True)
    path = backups / '.lock'
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if info.st_uid != 0 or not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise Unsafe('Unsafe lock file')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def validate_mappings(path, user):
    secure(path)
    entries = [line for line in path.read_text().splitlines() if line.startswith(user + ':')]
    if len(entries) != 1 or not re.fullmatch(re.escape(user) + r':\S+,\S+(?::\S+,\S+)*', entries[0]):
        raise Unsafe('Enroll a valid mapping for the invoking user before installation')


def main(argv=None):
    parser = argparse.ArgumentParser(description='YubiKey sudo authentication with native fallback')
    parser.add_argument('--version', action='version', version=f'sudo-yubikey {VERSION}')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--install', action='store_true')
    actions.add_argument('--disable', action='store_true')
    actions.add_argument('--status', action='store_true')
    parser.add_argument('--dry-run', action='store_true', help='Show configuration changes without writing')
    parser.add_argument('--module', type=Path, help='Absolute pam_u2f.so path (required for installation)')
    parser.add_argument('--pin', action='store_true', help='Request PIN verification; requires compatible enrollment')
    parser.add_argument('--trust-homebrew-module', action='store_true', help='Explicitly trust a user-managed PAM module and its libraries')
    args = parser.parse_args(argv)
    if not any((args.install, args.disable, args.status)):
        parser.print_help()
        return 0
    if sys.platform != 'darwin':
        raise Unsafe('Supported only on macOS 14 or later')
    major = int(subprocess.check_output(['/usr/bin/sw_vers', '-productVersion'], text=True).split('.')[0])
    if major < 14:
        raise Unsafe('Supported only on macOS 14 or later')
    paths = [Path('/etc/pam.d/sudo'), Path('/etc/pam.d/sudo_local')]
    # /etc is Apple's symlink to /private/etc; resolve that known alias only.
    paths = [Path('/private') / p.relative_to('/') for p in paths]
    for p in paths:
        secure(p.parent, directory=True)
        if p.exists() or p.is_symlink():
            secure(p)
    if args.status:
        for p in paths:
            print(f'{p}:')
            print(p.read_text() if p.exists() else '(absent)')
        print('Hardware authentication and sudo timestamp behavior have not been tested here.')
        return 0
    if args.install and not args.module:
        raise Unsafe('--module is required')
    if args.install:
        if not args.module.is_absolute() or args.module.name != 'pam_u2f.so':
            raise Unsafe('Expected an absolute pam_u2f.so path')
        module = args.module.resolve(strict=True)
        if not module.is_file():
            raise Unsafe('PAM module is not a regular file')
        if args.trust_homebrew_module:
            print('WARNING: you explicitly trust this module and its dependent libraries as root.', file=sys.stderr)
        else:
            secure(module)
            # A root-owned module alone cannot prove its dependent dylibs are root-controlled.
            libraries = subprocess.check_output(['/usr/bin/otool', '-L', str(module)], text=True)
            for line in libraries.splitlines()[1:]:
                dependency = line.strip().split(' (', 1)[0]
                if dependency.startswith(('/usr/lib/', '/System/Library/')):
                    continue
                raise Unsafe('Non-system dependent libraries need an administrator audit; use explicit trust only if accepted')
        user = os.environ.get('SUDO_USER') or os.environ.get('USER', '')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', user):
            raise Unsafe('Cannot determine invoking user')
        validate_mappings(Path('/private/etc/u2f_mappings'), user)
    else:
        module = None
    content = [p.read_text() if p.exists() else '' for p in paths]
    rendered = render(*content, module=module, pin=args.pin)
    changes = {p: text.encode() for p, text, old in zip(paths, rendered, content) if text != old}
    if args.dry_run:
        for p, data in changes.items():
            print(f'Would update {p}:\n{data.decode()}')
        print('No writes performed.')
        return 0
    if os.geteuid() != 0:
        raise Unsafe('Use an administrator recovery shell for configuration changes')
    if Path('/Library/LaunchDaemons/com.sudo-yubikey.plist').exists():
        raise Unsafe('Legacy boot daemon exists; remove it before changing PAM configuration')
    backups = Path('/private/var/db/sudo-yubikey')
    secure(backups.parent, directory=True)
    if not backups.exists():
        backups.mkdir(mode=0o700)
    with locked(backups):
        # Re-read under lock to avoid stale plans among cooperating invocations.
        fresh = [p.read_text() if p.exists() else '' for p in paths]
        if fresh != content:
            raise Unsafe('PAM configuration changed during preflight; retry')
        folder = transaction(changes, backups)
    print(f'Configuration updated. Recovery backup: {folder}' if folder else 'Already configured; no writes.')
    print('Keep your recovery shell open until fresh sudo authentication succeeds.')
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except (Unsafe, OSError, subprocess.SubprocessError, ValueError) as error:
        print(f'sudo-yubikey: {error}', file=sys.stderr)
        sys.exit(1)
