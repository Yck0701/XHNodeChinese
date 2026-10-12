import copy
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import community
import contribution_protocol as p
import manager_core as core
import app
from types import SimpleNamespace
from unittest.mock import Mock


def fixtures():
    engine={'version':'5.8.3','sha256':{n:'a'*64 for n in p.ENGINE_FILES}}
    return engine,{'schema':1,'engines':[{'engine':engine}]}


def dll():
    data=bytearray(300);data[:2]=b'MZ';struct.pack_into('<I',data,60,128)
    data[128:132]=b'PE\0\0';struct.pack_into('<H',data,132,0x8664);struct.pack_into('<H',data,150,0x2000)
    return bytes(data)


class CommunityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.engine,self.catalog=fixtures()

    def tearDown(self):self.tmp.cleanup()

    def result(self,custom=False):
        engine=copy.deepcopy(self.engine)
        if custom:engine['sha256'][p.ENGINE_FILES[0]]='b'*64
        return dict(engine=engine,catalog=self.catalog,state='missing',kind='custom' if custom else 'official',plugin_version='0.2.14')

    def package(self,result):
        path=self.root/'build.zip'
        with zipfile.ZipFile(path,'w') as z:
            base='XHNodeChinese/'
            z.writestr(base+'XHNodeChinese.uplugin',json.dumps({'VersionName':'0.2.14'}))
            for i,name in enumerate(p.MANIFESTS):
                binary=('XHSlateBridge0214.dll','XHModuleIndex0214.dll')[i]
                z.writestr(base+'Binaries/Win64/'+binary,dll())
                z.writestr(base+'Binaries/Win64/'+name,json.dumps(dict(engine_sha256=result['engine']['sha256'],bridge_file=binary,bridge_sha256=p.sha(dll()),private_path='C:/private')))
            for name in ('Dictionaries/User.csv','Saved/secret.json','Source/secret.cpp','Content/Python/private.py','BUILD_INFO.json'):
                z.writestr(base+name,'PRIVATE DATA')
        core.write_json(path.with_suffix('.json'),dict(sha256=core.digest(path),engine=result['engine']))
        return path

    def bundle(self,custom=False,consent=False):
        r=self.result(custom);return community.prepare(self.package(r),r,self.root/'out',consent)[0]

    def mutate(self,path,fn):
        with zipfile.ZipFile(path) as z:files={n:z.read(n) for n in z.namelist()}
        fn(files)
        with zipfile.ZipFile(path,'w') as z:
            for n,data in files.items():z.writestr(n,data)

    def test_official_requires_all_fingerprints(self):
        self.assertEqual(p.official_kind(self.engine,self.catalog),'official')
        changed=copy.deepcopy(self.engine);changed['sha256'][p.ENGINE_FILES[-1]]='f'*64
        changed['IsLicenseeVersion']=0;changed['BranchName']='++UE5+Release-5.8'
        self.assertEqual(p.official_kind(changed,self.catalog),'custom')

    def test_missing_hash_is_not_official(self):
        bad=copy.deepcopy(self.engine);bad['sha256'].pop(p.ENGINE_FILES[-1])
        with self.assertRaises(ValueError):p.official_kind(bad,self.catalog)

    def test_fingerprint_independent_of_local_paths(self):
        other=dict(self.engine,path='C:/Private',changelist=123)
        self.assertEqual(p.fingerprint(other),p.fingerprint(self.engine))

    def test_version_and_kind_have_separate_storage(self):
        tag=p.release_tag(self.engine,'0.2.14','official')
        self.assertNotEqual(tag,p.release_tag(self.engine,'0.2.15','official'))
        self.assertNotEqual(tag,p.release_tag(self.engine,'0.2.14','custom'))

    def test_official_bundle_removes_personal_source_and_scripts(self):
        path=self.bundle();meta=p.validate_bundle(path,self.catalog)
        self.assertEqual(meta['kind'],'official')
        with zipfile.ZipFile(path) as z:
            self.assertEqual(len(z.namelist()),5)
            self.assertFalse(any(b'PRIVATE DATA' in z.read(n) or b'C:/private' in z.read(n) for n in z.namelist()))

    def test_custom_requires_consent_before_writing(self):
        with self.assertRaises(ValueError):self.bundle(custom=True)
        self.assertFalse((self.root/'out').exists())
        path=self.bundle(custom=True,consent=True)
        self.assertTrue(p.validate_bundle(path,self.catalog)['custom_consent'])

    def test_tampered_binary_rejected(self):
        path=self.bundle();self.mutate(path,lambda f:f.update({'Binaries/Win64/XHSlateBridge0214.dll':dll()+b'tamper'}))
        with self.assertRaises(ValueError):p.validate_bundle(path,self.catalog)

    def test_official_claim_cannot_override_catalog(self):
        path=self.bundle(custom=True,consent=True)
        def mutate(files):
            meta=json.loads(files['contribution.json']);meta['kind']='official';files['contribution.json']=p.canonical(meta)
        self.mutate(path,mutate)
        with self.assertRaises(ValueError):p.validate_bundle(path,self.catalog)

    def test_unknown_fields_rejected_server_side(self):
        path=self.bundle()
        def mutate(files):
            meta=json.loads(files['contribution.json']);meta['private_path']='C:/secret';files['contribution.json']=p.canonical(meta)
        self.mutate(path,mutate)
        with self.assertRaises(ValueError):p.validate_bundle(path,self.catalog)

    def test_extra_files_and_traversal_rejected(self):
        path=self.bundle();self.mutate(path,lambda f:f.update({'../secret':'x'}))
        with self.assertRaises(ValueError):p.validate_bundle(path,self.catalog)

    def test_available_package_prevents_duplicate(self):
        feed={'plugins':[dict(engine=self.engine,version='0.2.14',verified=True)]}
        with patch.object(community,'read_json',return_value=self.catalog) as request,patch.object(core,'load_feed',return_value=feed):
            r=community.check(self.engine,'0.2.14',self.root)
        self.assertEqual(r['state'],'available');self.assertEqual(request.call_count,1)

    def test_pending_dedup_and_no_private_fingerprint_request(self):
        engine=self.result(True)['engine'];tag=p.release_tag(engine,'0.2.14','custom')
        index={'schema':1,'builds':{tag:{'state':'pending_review'}}}
        with patch.object(community,'read_json',side_effect=[self.catalog,index]) as request,patch.object(core,'load_feed',return_value={'plugins':[]}):
            r=community.check(engine,'0.2.14',self.root)
        self.assertEqual(r['state'],'pending_review')
        self.assertTrue(all(p.fingerprint(engine) not in c.args[0] and 'b'*64 not in c.args[0] for c in request.call_args_list))

    def test_offline_does_not_report_missing(self):
        with patch.object(community,'read_json',side_effect=OSError('offline')):
            with self.assertRaises(OSError):community.check(self.engine,'0.2.14',self.root)

    def test_existing_state_cannot_prepare_upload(self):
        r=self.result();package=self.package(r);r['state']='pending_review'
        with self.assertRaises(ValueError):community.prepare(package,r,self.root/'out')

    def test_issue_body_contains_consent_only_for_custom(self):
        path=self.bundle(custom=True,consent=True);meta=p.validate_bundle(path,self.catalog)
        body=community.issue_body(meta,core.digest(path))
        self.assertIn('- [x] 我同意公开分享',body)
        self.assertIn('XH-CONTRIBUTION-SHA256:',body)

    def test_declining_custom_prompt_never_prepares_or_opens_browser(self):
        r=self.result(True);package=self.package(r)
        ui=SimpleNamespace(show_cloud_result=Mock(),cloud_status=Mock(),log=Mock(),open_path=Mock())
        ui.start=lambda fn,done:done(fn())
        with patch.object(community,'check',return_value=r),patch.object(app.messagebox,'askyesno',return_value=False),patch.object(community,'prepare') as prepare,patch.object(app.webbrowser,'open') as browser:
            app.App.submit_compiled(ui,package)
        prepare.assert_not_called();browser.assert_not_called();ui.open_path.assert_not_called()

    def test_official_missing_prepares_without_custom_prompt(self):
        r=self.result();package=self.package(r)
        ui=SimpleNamespace(show_cloud_result=Mock(),cloud_status=Mock(),log=Mock(),open_path=Mock())
        ui.start=lambda fn,done:done(fn())
        with patch.object(community,'check',return_value=r),patch.object(app.messagebox,'askyesno',return_value=False) as ask,patch.object(community,'prepare',return_value=(self.root/'upload.zip','https://github.com')) as prepare:
            app.App.submit_compiled(ui,package)
        prepare.assert_called_once();self.assertEqual(prepare.call_args.args[-1],False)
        self.assertEqual(ask.call_count,1);self.assertEqual(ask.call_args.args[0],'提交到 GitHub')

    def test_cloud_existing_never_uploads(self):
        r=self.result();package=self.package(r);r['state']='pending_review'
        ui=SimpleNamespace(show_cloud_result=Mock(),cloud_status=Mock(),log=Mock())
        ui.start=lambda fn,done:done(fn())
        with patch.object(community,'check',return_value=r),patch.object(app.messagebox,'showinfo'),patch.object(community,'prepare') as prepare,patch.object(app.messagebox,'askyesno') as ask:
            app.App.submit_compiled(ui,package)
        prepare.assert_not_called();ask.assert_not_called()


if __name__=='__main__':unittest.main()
