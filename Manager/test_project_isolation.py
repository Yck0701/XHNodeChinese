"""Real directory links cannot redirect updates into a second project."""
from pathlib import Path
import os, subprocess, tempfile, unittest
from unittest.mock import patch
import manager_core as c

@unittest.skipUnless(os.name=='nt','Windows junction protection')
class IsolationTests(unittest.TestCase):
    def test_project_and_saved_junctions_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();other=root/'OtherProject';other.mkdir()
            (other/'Other.uproject').write_text('{}');sentinel=other/'Keep.txt';sentinel.write_bytes(b'untouched')
            alias=root/'Alias'
            subprocess.run(['cmd.exe','/d','/c','mklink','/J',str(alias),str(other)],check=True,
                           capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                with self.assertRaisesRegex(ValueError,'目录联接'):c.project_path(alias)
                with self.assertRaisesRegex(ValueError,'目录联接'):c.project_path(alias/'Other.uproject')
                self.assertEqual(sentinel.read_bytes(),b'untouched')
                self.assertEqual({p.name for p in other.iterdir()},{'Other.uproject','Keep.txt'})
            finally:alias.rmdir()
            project=root/'Project';project.mkdir();(project/'Project.uproject').write_text('{}')
            redirected=project/'Saved'
            subprocess.run(['cmd.exe','/d','/c','mklink','/J',str(redirected),str(other)],check=True,
                           capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                with self.assertRaisesRegex(ValueError,'目录联接'):c.backup(project)
                self.assertEqual({p.name for p in other.iterdir()},{'Other.uproject','Keep.txt'})
            finally:redirected.rmdir()

if __name__=='__main__':unittest.main()
