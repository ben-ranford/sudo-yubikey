import contextlib
import importlib.util
import io
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('tool', Path(__file__).parents[1] / 'sudo_yubikey.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
MAIN = '# sudo\nauth include sudo_local\nauth sufficient pam_smartcard.so\nauth required pam_opendirectory.so\naccount required pam_permit.so\n'
LOCAL = '# Native TouchID\nauth sufficient pam_tid.so\n'
MODULE = Path('/Library/Security/pam_u2f.so')
OLD = '# YubiKey U2F authentication (primary)\nauth sufficient /opt/homebrew/lib/pam/pam_u2f.so authfile=/etc/u2f_mappings cue nouserok\n'

class Rendering(unittest.TestCase):
    def test_fallback_and_no_bypass(self):
        main, local = tool.render(MAIN, LOCAL, MODULE)
        self.assertEqual(main, MAIN)
        self.assertIn('auth sufficient /Library/Security/pam_u2f.so', local)
        self.assertNotIn('nouserok', local)
        self.assertIn('userpresence=1 pinverification=0 userverification=0', local)
        self.assertTrue(local.endswith(LOCAL))
    def test_pin_policy(self):
        _, local = tool.render(MAIN, LOCAL, MODULE, True)
        self.assertIn('pinverification=1', local)
        self.assertNotIn('pinverification=0', local)
    def test_idempotent(self):
        first = tool.render(MAIN, LOCAL, MODULE)
        self.assertEqual(tool.render(*first, MODULE), first)
    def test_migrate_known_legacy(self):
        main, local = tool.render('# sudo\n' + OLD + MAIN.split('\n', 1)[1], LOCAL, MODULE)
        self.assertEqual(main, MAIN)
        self.assertEqual(local.count('pam_u2f.so'), 1)
    def test_disable_preserves_native(self):
        installed = tool.render(MAIN, LOCAL, MODULE)
        self.assertEqual(tool.render(*installed), (MAIN, LOCAL))
    def test_disable_idempotent(self):
        self.assertEqual(tool.render(MAIN, LOCAL), (MAIN, LOCAL))
    def test_other_u2f_refused(self):
        with self.assertRaises(tool.Unsafe):
            tool.render(MAIN, 'auth required pam_u2f.so authfile=/another/file\n', MODULE)
    def test_whitespace_attack(self):
        for path in ['/tmp/a b/pam_u2f.so', '/tmp/x\nauth sufficient pam_permit.so', 'relative.so', '/tmp/x;foo']:
            with self.subTest(path=path), self.assertRaises(tool.Unsafe):
                tool.render(MAIN, LOCAL, path)
    def test_missing_include(self):
        with self.assertRaises(tool.Unsafe):
            tool.render(MAIN.replace('auth include sudo_local\n', ''), LOCAL, MODULE)
    def test_missing_password(self):
        with self.assertRaises(tool.Unsafe):
            tool.render(MAIN.replace('auth required pam_opendirectory.so\n', ''), LOCAL, MODULE)
    def test_preempting_auth(self):
        with self.assertRaises(tool.Unsafe):
            tool.render(MAIN.replace('auth include', 'auth sufficient pam_tid.so\nauth include'), LOCAL, MODULE)
    def test_empty_local(self):
        _, local = tool.render(MAIN, '', MODULE)
        self.assertIn('pam_u2f.so', local)
    def test_comments_preserved(self):
        text = '# another tool mentions pam_u2f.so\n' + LOCAL
        self.assertTrue(tool.render(MAIN, text, MODULE)[1].endswith(text))
    def test_duplicate_rules_removed(self):
        _, local = tool.render(MAIN, OLD + OLD + LOCAL, MODULE)
        self.assertEqual(local.count('pam_u2f.so'), 1)

class Files(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backups = self.root / 'backups'
        self.backups.mkdir()
        self.a = self.root / 'sudo'
        self.b = self.root / 'sudo_local'
        self.a.write_bytes(b'original main\n')
        self.a.chmod(0o444)
    def test_atomic_replace_mode(self):
        tool.atomic(self.a, b'new\n', 0o444)
        self.assertEqual(self.a.read_bytes(), b'new\n')
        self.assertEqual(stat.S_IMODE(self.a.stat().st_mode), 0o444)
    def test_success_backup(self):
        folder = tool.transaction({self.a:b'new', self.b:b'local'}, self.backups)
        self.assertEqual((folder/'0').read_bytes(), b'original main\n')
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((folder/'0').stat().st_mode), 0o600)
        self.assertEqual(self.a.read_bytes(), b'new')
        self.assertEqual(self.b.read_bytes(), b'local')
        self.assertEqual(stat.S_IMODE(self.a.stat().st_mode), 0o444)
    def test_noop_no_backup(self):
        self.assertIsNone(tool.transaction({}, self.backups))
        self.assertEqual(list(self.backups.iterdir()), [])
    def test_failure_rolls_back_existing_and_created(self):
        def failing(path, data, mode):
            tool.atomic(path, data, mode)
            if path == self.a:
                raise OSError('injected after replacement')
        with self.assertRaises(OSError):
            tool.transaction({self.b:b'created',self.a:b'changed'}, self.backups, failing)
        self.assertFalse(self.b.exists())
        self.assertEqual(self.a.read_bytes(), b'original main\n')
        self.assertEqual(stat.S_IMODE(self.a.stat().st_mode), 0o444)
    def test_backup_failure_no_writes(self):
        with patch.object(Path, 'write_bytes', side_effect=OSError('backup failed')):
            with self.assertRaises(OSError):
                tool.transaction({self.a:b'changed'}, self.backups)
        self.assertEqual(self.a.read_bytes(), b'original main\n')
    def test_unique_backups(self):
        one = tool.transaction({self.a:b'one'}, self.backups)
        two = tool.transaction({self.a:b'two'}, self.backups)
        self.assertNotEqual(one,two)
    def test_atomic_failed_replace_leaves_original(self):
        with patch.object(os, 'replace', side_effect=OSError('replace failed')):
            with self.assertRaises(OSError):
                tool.atomic(self.a,b'changed')
        self.assertEqual(self.a.read_bytes(),b'original main\n')
        self.assertFalse(list(self.root.glob('.sudo-yubikey-*')))
    def test_interrupt_rollback(self):
        with self.assertRaises(KeyboardInterrupt):
            tool.transaction({self.a:b'changed'},self.backups,lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()))
        self.assertEqual(self.a.read_bytes(),b'original main\n')
    def test_mapping_no_disclosure(self):
        self.b.write_text('ben:handle,key,es256,+presence\nother:handle,key\n')
        with patch.object(tool,'secure'):
            tool.validate_mappings(self.b,'ben')
            for data in ['', 'other:handle,key\n', 'ben:\n', 'ben:h,k\nben:h2,k2\n']:
                self.b.write_text(data)
                with self.assertRaises(tool.Unsafe):
                    tool.validate_mappings(self.b,'ben')
    def test_secure_rejects_user_ownership(self):
        with self.assertRaises(tool.Unsafe):
            tool.secure(self.a)
    def test_secure_rejects_symlink(self):
        self.b.symlink_to(self.a)
        with self.assertRaises(tool.Unsafe):
            tool.secure(self.b)

class CLI(unittest.TestCase):
    def test_no_args_no_mutation(self):
        with patch.object(tool,'transaction',side_effect=AssertionError('write')), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tool.main([]),0)
    def test_version(self):
        with contextlib.redirect_stdout(io.StringIO()) as output, self.assertRaises(SystemExit) as result:
            tool.main(['--version'])
        self.assertEqual(result.exception.code,0)
        self.assertIn('2.0.0', output.getvalue())
    def test_removed_unsafe_options(self):
        for flag in ['--require-key','--install-daemon','--setup-keys','--install-deps']:
            with self.subTest(flag=flag), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                tool.main([flag])
    def test_actions_exclusive(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            tool.main(['--install','--disable'])
    def test_nonmac_refused(self):
        with patch.object(tool.sys,'platform','linux'), self.assertRaises(tool.Unsafe):
            tool.main(['--install','--module','/tmp/pam_u2f.so'])
    def test_old_macos_refused(self):
        with patch.object(tool.sys,'platform','darwin'), patch.object(tool.subprocess,'check_output',return_value='13.6.1'), self.assertRaises(tool.Unsafe):
            tool.main(['--disable'])

if __name__ == '__main__':
    unittest.main()

class AdversarialLayouts(unittest.TestCase):
    def test_comment_cannot_hide_preemption(self):
        main = '# sudo_local in comment\nauth sufficient pam_tid.so\n' + MAIN
        with self.assertRaises(tool.Unsafe):
            tool.render(main, LOCAL, MODULE)
    def test_duplicate_include(self):
        with self.assertRaises(tool.Unsafe):
            tool.render(MAIN + 'auth include sudo_local\n', LOCAL, MODULE)
    def test_custom_required_factor_preserved_by_refusal(self):
        with self.assertRaises(tool.Unsafe):
            tool.render(MAIN + 'auth required pam_custom.so\n', LOCAL, MODULE)
    def test_custom_local_refused(self):
        for line in ['auth required pam_other.so\n', 'account required pam_other.so\n', 'auth optional /opt/homebrew/lib/pam/pam_reattach.so\n']:
            with self.subTest(line=line), self.assertRaises(tool.Unsafe):
                tool.render(MAIN, LOCAL + line, MODULE)
    def test_disable_preserves_custom_non_u2f(self):
        local = LOCAL + 'auth required pam_other.so\n'
        self.assertEqual(tool.render(MAIN, OLD + local), (MAIN, local))

class CLIPreflight(unittest.TestCase):
    def setUp(self):
        self.stack=contextlib.ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(tool.sys,'platform','darwin'))
        self.stack.enter_context(patch.object(tool.subprocess,'check_output',side_effect=lambda argv,**kw: '14.0' if 'sw_vers' in argv[0] else '/Library/Security/pam_u2f.so:\n\t/usr/lib/libSystem.B.dylib (compatibility version 1.0)\n'))
        self.stack.enter_context(patch.object(tool,'secure'))
        self.stack.enter_context(patch.object(tool,'validate_mappings'))
        self.stack.enter_context(patch.object(tool,'locked',side_effect=lambda *a: contextlib.nullcontext()))
        self.tx=self.stack.enter_context(patch.object(tool,'transaction',return_value='/backup'))
        self.stack.enter_context(patch.object(os,'geteuid',return_value=0))
        self.stack.enter_context(patch.dict(os.environ,{'SUDO_USER':'ben'},clear=True))
        self.stack.enter_context(patch.object(Path,'resolve',return_value=MODULE))
        self.stack.enter_context(patch.object(Path,'is_file',return_value=True))
        self.stack.enter_context(patch.object(Path,'is_symlink',return_value=False))
        self.exists=self.stack.enter_context(patch.object(Path,'exists',side_effect=lambda p: str(p) != '/Library/LaunchDaemons/com.sudo-yubikey.plist',autospec=True))
        self.read=self.stack.enter_context(patch.object(Path,'read_text',autospec=True,side_effect=lambda p: MAIN if p.name=='sudo' else LOCAL))
        self.output=self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
    def test_dry_run_never_writes(self):
        self.assertEqual(tool.main(['--install','--module',str(MODULE),'--dry-run']),0)
        self.tx.assert_not_called()
    def test_disable_dry_run(self):
        self.assertEqual(tool.main(['--disable','--dry-run']),0)
        self.tx.assert_not_called()
    def test_install_success(self):
        self.assertEqual(tool.main(['--install','--module',str(MODULE)]),0)
        changes=self.tx.call_args.args[0]
        self.assertEqual(set(changes),{Path('/private/etc/pam.d/sudo_local')})
        self.assertNotIn(b'nouserok',next(iter(changes.values())))
    def test_missing_module(self):
        with self.assertRaises(tool.Unsafe): tool.main(['--install'])
        self.tx.assert_not_called()
    def test_relative_module_refused(self):
        with self.assertRaises(tool.Unsafe): tool.main(['--install','--module','pam_u2f.so'])
        self.tx.assert_not_called()
    def test_nonroot_never_writes(self):
        with patch.object(os,'geteuid',return_value=501), self.assertRaises(tool.Unsafe):
            tool.main(['--install','--module',str(MODULE)])
        self.tx.assert_not_called()
    def test_daemon_refuses_changes(self):
        self.exists.side_effect=lambda p: True
        with self.assertRaises(tool.Unsafe): tool.main(['--install','--module',str(MODULE)])
        self.tx.assert_not_called()
    def test_dependent_library_refused(self):
        with patch.object(tool.subprocess,'check_output',side_effect=['14.0',str(MODULE)+':\n\t/opt/homebrew/lib/libfido2.dylib (compatibility version 1)\n']), self.assertRaises(tool.Unsafe):
            tool.main(['--install','--module',str(MODULE)])
        self.tx.assert_not_called()
    def test_explicit_module_trust(self):
        with contextlib.redirect_stderr(io.StringIO()) as output:
            self.assertEqual(tool.main(['--install','--module',str(MODULE),'--trust-homebrew-module','--dry-run']),0)
        self.assertIn('explicitly trust',output.getvalue())
        self.tx.assert_not_called()
    def test_changed_config_refused(self):
        self.read.side_effect=[MAIN,LOCAL,MAIN+'# concurrent edit\n',LOCAL]
        with self.assertRaises(tool.Unsafe): tool.main(['--install','--module',str(MODULE)])
        self.tx.assert_not_called()
    def test_status_never_writes(self):
        self.assertEqual(tool.main(['--status']),0)
        self.tx.assert_not_called()
