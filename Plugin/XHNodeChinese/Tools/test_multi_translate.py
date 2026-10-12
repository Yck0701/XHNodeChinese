import json, sys, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'Content/Python'))
from xh_node_chinese import core, multi_translate as mt, personal
from xh_node_chinese.live import append_pairs

LONG = 'Uses {Value} for 2 frames to adjust the initial particle lifetime and evaluates Particles.Age before updating the particle.'

class TranslationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.plugin = Path(self.tmp.name)/'Plugin'; self.save = Path(self.tmp.name)/'Saved'
        (self.plugin/'Dictionaries').mkdir(parents=True); self.save.mkdir()
        self.user = self.plugin/'Dictionaries/User.csv'; self.user.write_bytes(b'Key,Value\n')
        core.atomic_write(self.save/'Live.csv', append_pairs(b'Key,Value\n', {'Sprite Size':'','Shape Normal':''}))
        core.atomic_write(self.save/'LongText.csv', append_pairs(b'Key,Value\n', {LONG:''}))

    def response(self, batch):
        return {'request_id':batch['request_id'], 'translations':[
            {'id':i['id'], 'translation':'在2帧内使用 {Value} 调整粒子的初始寿命，更新前计算 Particles.Age。' if i['kind']=='long' else '中文名称'}
            for i in batch['items']], 'skipped':[]}

    def session(self, provider='doubao'):
        s=mt.Session(self.plugin,self.save)
        self.assertTrue(s.prepare({'Sprite':'精灵'},provider))
        return s

    def test_web_no_codex_needed_restart_fenced_json_and_complete(self):
        s=self.session(); text,path=s.web_prompt()
        self.assertIn('精灵',text); self.assertTrue(path.is_file())
        self.assertNotIn(LONG,text)
        response=self.response(s.current_batch()[1])
        s.accept_text('```json\n'+json.dumps(response,ensure_ascii=False)+'\n```')
        self.assertTrue(s.poll()); self.assertEqual(s.state['completed'],2)
        s=mt.Session(self.plugin,self.save)
        self.assertTrue(s.prepare({},'doubao'))
        s.accept_text(json.dumps(self.response(s.current_batch()[1])))
        self.assertTrue(s.poll()); self.assertEqual(s.state['phase'],'done')
        self.assertTrue(json.loads((Path(s.state['folder'])/'applied.json').read_text(encoding='utf-8'))['complete'])

    def test_bad_results_and_repeat_do_not_modify_dictionary(self):
        s=self.session(); batch=s.current_batch()[1]; good=self.response(batch)
        before=self.user.read_bytes()
        for damage in ('duplicate','unknown','request'):
            data=json.loads(json.dumps(good))
            if damage=='missing':data['translations'].pop()
            if damage=='duplicate':data['translations'].append(data['translations'][0])
            if damage=='unknown':data['translations'][0]['id']='unknown'
            if damage=='request':data['request_id']='wrong'
            with self.assertRaises(ValueError):s.accept_text(json.dumps(data))
            self.assertEqual(self.user.read_bytes(),before)
        s.accept_text(json.dumps(good));s.poll()
        with self.assertRaises(ValueError):s.accept_text(json.dumps(good))

    def test_manual_edit_preserved_and_cancel_late_response(self):
        s=self.session(); response=self.response(s.current_batch()[1])
        personal.update(self.plugin,self.save,{'Sprite Size':'用户尺寸'})
        s.accept_text(json.dumps(response));s.poll()
        rows={r['Source']:r['Translation'] for r in core.load_dictionary(self.user)}
        self.assertEqual(rows['Sprite Size'],'用户尺寸')
        s.cancel()
        with self.assertRaises(ValueError):s.accept_text(json.dumps(response))

    def test_path_identifier_number_and_placeholder_guards(self):
        batch={'request_id':'a','items':[{'id':'1','kind':'long','source':LONG+' /Game/FX/Asset.Asset'}]}
        valid={'request_id':'a','translations':[{'id':'1','translation':'在2帧内使用 {Value} 更新 Particles.Age，路径 /Game/FX/Asset.Asset。'}],'skipped':[]}
        mt.validate_batch(batch,valid)
        for token in ('{Value}','Particles.Age','/Game/FX/Asset.Asset','2'):
            data=json.loads(json.dumps(valid));data['translations'][0]['translation']=data['translations'][0]['translation'].replace(token,'')
            with self.assertRaises(ValueError):mt.validate_batch(batch,data)

    def test_bounded_batches_and_noise(self):
        items=[{'id':str(i),'kind':'term','source':'Term '+str(i)} for i in range(25)]
        items += [{'id':str(i),'kind':'long','source':'English description '*60} for i in range(25,30)]
        groups=mt.batches({'items':items})
        self.assertEqual([len(b['items']) for b in groups],[24,1,3,2])
        self.assertEqual(sum(len(b['items']) for b in groups),30)
        self.assertFalse(mt.meaningful('py module.function()'))
        self.assertFalse(mt.meaningful('路径：/Game/Asset.Asset\n* 脚本未公开给库。'))
        self.assertTrue(mt.meaningful('An English explanation.\n路径：/Game/Asset.Asset'))

    def config(self):
        core.write_json(self.save/'TranslationAPI.json',{'endpoint':'https://example.com/v1/chat/completions',
                        'model':'model-name','api_key':'secret-test-key','extra_body':{}})
        return mt.api_config(self.save)

    def test_config_environment_and_no_replacement(self):
        self.config();old=(self.save/'TranslationAPI.json').read_bytes()
        mt.configure_api(self.save,'doubao');self.assertEqual((self.save/'TranslationAPI.json').read_bytes(),old)
        data=json.loads(old);data['api_key']='';data['api_key_env']='XH_TEST_KEY'
        core.write_json(self.save/'TranslationAPI.json',data)
        with patch.dict('os.environ',{'XH_TEST_KEY':'env-secret'}):self.assertEqual(mt.api_config(self.save)['api_key'],'env-secret')
        for endpoint in ('http://example.com/v1/chat/completions','https://name:secret@example.com/chat/completions','https://example.com/chat/completions?key=secret'):
            data['endpoint']=endpoint;core.write_json(self.save/'TranslationAPI.json',data)
            with self.assertRaises(ValueError):mt.api_config(self.save)

    def test_api_batches_failure_redacted_resume_only_remaining(self):
        s=self.session('api');config=self.config();calls=[]
        def failing(config,batch):
            calls.append(batch)
            if len(calls)==2:raise RuntimeError('network '+config['api_key'])
            return self.response(batch)
        s.start_api(config,failing);s.worker.join(3);s.poll()
        self.assertEqual(s.state['completed'],2);self.assertEqual(s.state['phase'],'error')
        self.assertNotIn(config['api_key'],s.path.read_text(encoding='utf-8'))
        s=mt.Session(self.plugin,self.save)
        remaining=[]
        def okay(config,batch):remaining.extend(i['id'] for i in batch['items']);return self.response(batch)
        s.start_api(config,okay);s.worker.join(3);s.poll()
        self.assertEqual(len(remaining),1);self.assertEqual(s.state['phase'],'done')

    def test_api_cancel_inflight_discards_returned_batch(self):
        s=self.session('api');entered=threading.Event();finish=threading.Event()
        def delayed(config,batch):entered.set();finish.wait(2);return self.response(batch)
        s.start_api(self.config(),delayed);self.assertTrue(entered.wait(1));s.cancel();finish.set();s.worker.join(3)
        self.assertFalse(s.poll());self.assertEqual(s.state['phase'],'cancelled')
        self.assertEqual(list(Path(s.state['folder']).glob('response-*.json')),[])

    def test_http_payload_and_error_does_not_log_server_body(self):
        s=self.session('api');batch=s.current_batch()[1];config=self.config()
        class Response:
            def __enter__(inner):return inner
            def __exit__(inner,*args):pass
            def read(inner,n):return json.dumps({'choices':[{'message':{'content':json.dumps(self.response(batch))},'finish_reason':'stop'}]}).encode()
        with patch.object(mt.http,'build_opener') as opener:
            opener.return_value.open.return_value=Response()
            mt.api_translate(config,batch)
            req=opener.return_value.open.call_args.args[0]
            body=json.loads(req.data);self.assertFalse(body['stream']);self.assertEqual(body['model'],'model-name')
            self.assertNotIn(config['api_key'],req.data.decode())
            opener.return_value.open.side_effect=HTTPError(config['endpoint'],401,'secret-test-key',{},None)
            with self.assertRaises(RuntimeError) as caught:mt.api_translate(config,batch)
            self.assertNotIn(config['api_key'],str(caught.exception));self.assertIn('401',str(caught.exception))

if __name__=='__main__':unittest.main()
