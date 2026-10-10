import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Content/Python'))
from xh_node_chinese import core,codex_translate
from xh_node_chinese.live import useful,append_pairs,LiveSession

class CaptureNoiseTests(unittest.TestCase):
    def test_filters_all_queues_without_losing_descriptions_or_user_edits(self):
        noise=['168.74 KiB','Ctrl + Alt','Ctrl+Shift+S','Alt','64 loaded','12.5 MiB/s']
        long='Samples the attributes from particles in another emitter and returns the result for use in the current simulation.\n路径：/Niagara/Modules/Test.Test'
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); plugin=root/'Plugin'; save=root/'Saved'
            (plugin/'Dictionaries').mkdir(parents=True);save.mkdir()
            core.atomic_write(plugin/'Dictionaries/User.csv',b'Key,Value\n')
            for name in ('Live.csv','Pending.csv','LongText.csv'):
                core.atomic_write(save/name,append_pairs(b'Key,Value\n',dict.fromkeys(noise,'')))
            core.atomic_write(save/'LongText.csv',append_pairs((save/'LongText.csv').read_bytes(),{long:''}))
            self.assertEqual([i['source'] for i in codex_translate.collect(save,{},True)],[long])
            session=LiveSession(plugin,save)
            core.atomic_write(session.path,append_pairs(session.path.read_bytes(),{'Cmd':'命令','Color Roughness':''}))
            session.sync(noise,{})
            rows={r['Source']:r['Translation'] for r in core.load_dictionary(session.path,True)}
            self.assertEqual(rows,{'Cmd':'命令','Color Roughness':''})
            for value in noise:self.assertFalse(useful(value),value)
            for value in ('Control Rig','Shift Position','Memory Size','Load Asset','Vector3'):
                self.assertTrue(useful(value),value)

if __name__=='__main__':unittest.main()
