import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from xh_node_chinese import core,multi_translate as mt,codex_translate as ct,web_import as wi,asset_index
from xh_node_chinese.live import append_pairs

class Workflow(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.plugin=Path(self.tmp.name)/'Plugin';self.save=Path(self.tmp.name)/'Saved'
        (self.plugin/'Dictionaries').mkdir(parents=True);self.save.mkdir()
        (self.plugin/'Dictionaries/User.csv').write_bytes(b'Key,Value\n')
        core.atomic_write(self.save/'Live.csv',append_pairs(b'Key,Value\n',{'Sprite Size':'','Particle Color':''}))
        self.session=mt.Session(self.plugin,self.save);self.session.prepare({},'doubao')
        self.batch=self.session.current_batch()[1]

    def test_prose_json_partial_restart_and_markdown_resume(self):
        first,second=self.batch['items']
        data={'request_id':self.batch['request_id'],'translations':[{'id':first['id'],'translation':'精灵尺寸'}]}
        self.assertEqual(self.session.accept_text('翻译如下：\n```json\n'+json.dumps(data)+'\n```\n请查收。'),1)
        self.assertTrue(self.session.poll())
        restarted=mt.Session(self.plugin,self.save);restarted.cancel()
        self.assertTrue(restarted.prepare({},'doubao'))
        self.assertEqual(len(restarted.current_batch()[1]['items']),1)
        table='| 编号 | 中文 |\n|---|---|\n|'+second['id']+'|粒子颜色|'
        restarted.accept_text(table);self.assertTrue(restarted.poll())
        self.assertEqual(restarted.state['phase'],'done')
        self.assertEqual(len(list(Path(restarted.state['folder']).glob('response-*.json'))),2)
        self.assertEqual(len(list(Path(restarted.state['folder']).glob('answer-*.txt'))),2)

    def test_csv_original_binding_and_quoted_multiline(self):
        data,report=wi.normalize(self.batch,'"Sprite Size","精灵尺寸"\n"Particle Color","粒子颜色"')
        self.assertEqual(report['accepted'],2)
        batch={'request_id':'a','items':[{'id':'1','kind':'long','source':'Hello\nWorld'}]}
        self.assertEqual(wi.normalize(batch,'"Hello\nWorld","你好\n世界"')[0]['translations'][0]['translation'],'你好\n世界')

    def test_partial_invalid_preserves_placeholder_and_only_returns_valid(self):
        batch={'request_id':'a','items':[{'id':'1','kind':'long','source':'Use {Value} on Particles.Age for 2 frames.'},{'id':'2','kind':'term','source':'Sprite Size'}]}
        response={'translations':[{'id':'1','translation':'不完整译文'},{'id':'2','translation':'精灵尺寸'}]}
        data,report=wi.normalize(batch,json.dumps(response))
        self.assertEqual([i['id'] for i in data['translations']],['2'])
        self.assertEqual(report['remaining_ids'],['1'])
        self.assertTrue(report['rejected'])

    def test_unrelated_or_multiple_answers_never_import(self):
        for text in ('{"request_id":"other","translations":[]}',
                     '|Source|中文|\n|--|--|\n|Unknown Term|错误|',
                     '{"translations":[]}\n{"translations":[]}'):
            with self.assertRaises(ValueError):self.session.accept_text(text)
        self.assertEqual((self.plugin/'Dictionaries/User.csv').read_bytes(),b'Key,Value\n')

    def test_default_codex_needs_no_thread_or_four_paths(self):
        with patch.object(ct,'discover_cli',return_value=''):
            config=ct.connection(self.save)
            self.assertEqual(config['thread_id'],'')
            s=ct.Session(self.plugin,self.save);self.assertTrue(s.start({}))
            s.worker.join(2);s.poll()
        folder=Path(s.state['folder'])
        self.assertTrue((folder/'TRANSLATE.md').is_file())
        self.assertIn(str(folder/'TRANSLATE.md'),ct.handoff_text(folder))
        self.assertLess(len(ct.handoff_text(folder)),400)

    def test_failed_codex_resume_reuses_request(self):
        with patch.object(ct,'discover_cli',return_value=''):
            s=ct.Session(self.plugin,self.save)
            def fail(*args):raise RuntimeError('not connected')
            s.start({},sender=fail);s.worker.join(2);s.poll()
            folder=s.state['folder'];s.start({},sender=lambda *args:None);s.worker.join(2);s.poll()
            self.assertEqual(s.state['folder'],folder)
            self.assertEqual(s.state['phase'],'waiting')

    def test_asset_text_and_unopened_queue(self):
        self.assertEqual(asset_index.source_text('NSLOCTEXT("ns", "key", "Hello\\nWorld")'),'Hello\nWorld')
        self.assertEqual(asset_index.display_name('GPUUpdateParticle'),'GPU Update Particle')
        core.atomic_write(self.save/'Indexed.csv',append_pairs(b'Key,Value\n',{'Unopened Module':''}))
        self.assertIn('Unopened Module',{i['source'] for i in ct.collect(self.save,{})})

if __name__=='__main__':unittest.main()
