"""Regress the missing 14.50 toolset on a machine with a different UE-selected MSVC."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from msvc_toolchain import build_command, select_toolchain


class ToolchainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='xh-msvc-')
        self.base = Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)
        self.root = self.base / 'Visual Studio/2022/BuildTools/VC/Tools/MSVC/14.44.35207'
        self.vcvars = self.root.parents[2] / 'Auxiliary/Build/vcvars64.bat'
        self.compiler = self.root / 'bin/Hostx64/x64/cl.exe'
        self.linker = self.compiler.with_name('link.exe')
        for path in (self.vcvars, self.compiler, self.linker):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'')
        self.response = '/external:I "' + self.root.as_posix() + '/INCLUDE"\n'
        self.response += '/external:I "C:/Program Files (x86)/Windows Kits/10/include/10.0.26100.0/ucrt"\n'
        self.logs = []

    def select(self, response=None, requested='14.50', hint=None):
        return select_toolchain(self.response if response is None else response,
                                str(self.vcvars if hint is None else hint), requested, self.logs.append)

    def test_missing_fixed_1450_uses_ue_selected_1444(self):
        result = self.select()
        self.assertEqual(result['compiler'], self.compiler)
        self.assertEqual(result['version'], '14.44.35207')
        self.assertTrue(any('14.50' in line and '14.44.35207' in line for line in self.logs))

    def test_auto_and_matching_hint(self):
        for version in ('auto', '', '14.44', '14.44.35207'):
            self.logs.clear()
            self.assertEqual(self.select(requested=version)['version'], '14.44.35207')
            self.assertFalse(any('不一致' in line for line in self.logs))

    def test_another_visual_studio_hint_cannot_mix_compiler_and_headers(self):
        result = self.select(hint=self.base / 'DifferentVS/vcvars64.bat')
        self.assertEqual(result['vcvars'], self.vcvars)

    def test_windows_paths_and_compact_include_flag(self):
        self.response = self.response.replace('/external:I ', '/I').replace('/', '\\')
        self.response = self.response.replace('\\I', '/I')
        self.assertEqual(self.select()['compiler'], self.compiler)

    def test_missing_toolset_rejected_without_fallback(self):
        self.compiler.unlink()
        with self.assertRaisesRegex(ValueError, '14.44.35207.*不完整'):
            self.select()

    def test_missing_linker_rejected(self):
        self.linker.unlink()
        with self.assertRaisesRegex(ValueError, 'link.exe'):
            self.select()

    def test_missing_environment_script_rejected(self):
        self.vcvars.unlink()
        with self.assertRaisesRegex(ValueError, 'vcvars64.bat'):
            self.select()

    def test_unknown_or_conflicting_compiler_rejected(self):
        for response in ('/I "unrelated"', self.response + '/I "D:/Other/VC/Tools/MSVC/14.50.12345/include"'):
            with self.assertRaisesRegex(ValueError, '唯一 MSVC'):
                self.select(response=response)

    def test_conflicting_windows_sdks_rejected(self):
        with self.assertRaisesRegex(ValueError, '多个 Windows SDK'):
            self.select(response=self.response + '/I "C:/Program Files (x86)/Windows Kits/10/include/10.0.22621.0/um"')

    def test_command_pins_compiler_and_checks_environment(self):
        command = build_command(self.select(), self.base / '中文 路径/compile.rsp')
        self.assertIn('-vcvars_ver=14.44.35207', command)
        self.assertIn('10.0.26100.0', command)
        self.assertIn('"' + str(self.compiler) + '" @"', command)
        self.assertNotIn('\ncl ', command)
        self.assertIn('VCToolsInstallDir', command)
        self.assertTrue(command.endswith('exit /b %errorlevel%\n'))

    def test_command_special_character_rejected(self):
        with self.assertRaisesRegex(ValueError, '特殊字符'):
            build_command(self.select(), self.base / 'bad%name/compile.rsp')

    @unittest.skipUnless(os.name == 'nt', 'Windows batch execution')
    def test_vcvars_false_success_stops_before_compiler(self):
        self.vcvars.write_text('@echo off\nset VCToolsInstallDir=\nexit /b 0\n')
        cmd = self.base / 'build.cmd'
        cmd.write_text(build_command(self.select(), self.base / 'compile.rsp'), encoding='utf-8')
        result = subprocess.run(['cmd.exe', '/d', '/c', str(cmd)], capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn(b'did not initialize', result.stdout)


if __name__ == '__main__':
    unittest.main()
