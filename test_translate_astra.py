import contextlib, io, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import translate_json as t

class AstraTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
 def run_doc(self, entries, **kw):
  doc={'format':'astra-rpgm-translation','version':1,'sourceLanguage':'en','targetLanguage':'en','sourceHash':'unchanged','entries':entries}
  p=self.root/'input.json';p.write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8');out=self.root/'out.json'
  with patch.object(t.Ollama,'model_digest',return_value='test'),patch.object(t.Ollama,'translate',side_effect=kw.get('transform',lambda text,*a:text.replace('こんにちは','Hello'))),contextlib.redirect_stdout(io.StringIO()):
   code=t.run([str(p),'-o',str(out),'--cache',str(self.root/'cache.db'),'--report',str(self.root/'report.json'),'--retries','0'])
  return doc,json.loads(out.read_text(encoding="utf-8")),json.loads((self.root/'report.json').read_text(encoding='utf-8')),code
 def entry(self,source,**kw):return dict(source=source,translation='',protectedTokens=[],**kw)
 def test_only_translation_changes_and_identity_is_shared(self):
  entries=[self.entry('こんにちは',identityGroup='name'),self.entry('こんにちは',identityGroup='name'),self.entry('こんにちは',preserveOriginal=True)]
  old,new,report,code=self.run_doc(entries)
  self.assertEqual(code,0)
  self.assertEqual([e['translation'] for e in new['entries']],['Hello','Hello','こんにちは'])
  for e in new['entries']:e['translation']=''
  self.assertEqual(new,old)
 def test_markers_are_restored_and_repeated_text_cached(self):
  entries=[]
  for suffix in ['first','second']:
   marker=f'⟦ASTRA_{suffix}_0⟧';e=self.entry('こんにちは'+marker);e['protectedTokens']=[{'marker':marker,'value':'\\C[2]'}];entries.append(e)
  old,new,report,code=self.run_doc(entries)
  self.assertEqual(code,0);self.assertEqual(report['cache_hits'],1)
  for a,b in zip(old['entries'],new['entries']):self.assertEqual(b['translation'],a['source'].replace('こんにちは','Hello'))
 def test_invalid_generated_code_leaves_empty_and_flags_review(self):
  _,new,report,code=self.run_doc([self.entry('こんにちは')],transform=lambda *a:'Hello %s')
  self.assertEqual(code,0);self.assertEqual(new['entries'][0]['translation'],'');self.assertTrue(report['review'])
 def test_existing_translation_preserved(self):
  e=self.entry('こんにちは');e['translation']='Already done'
  _,new,_,code=self.run_doc([e]);self.assertEqual(new['entries'][0],e);self.assertEqual(code,0)
 def test_target_mismatch_fails_before_model(self):
  p=self.root/'in.json';p.write_text(json.dumps({'format':'astra-rpgm-translation','version':1,'targetLanguage':'fr','entries':[]}))
  with patch.object(t.Ollama,'model_digest',side_effect=AssertionError('network')),self.assertRaises(t.TranslationError):t.run([str(p)])
 def test_model_line_wrap_is_flattened_before_validation(self):
  c=t.Ollama('http://localhost','model')
  with patch.object(c,'request',return_value={'done':True,'done_reason':'stop','response':'Hello\nworld'}):self.assertEqual(c.translate('こんにちは','Japanese','English'),'Hello world')

if __name__=='__main__':unittest.main()

