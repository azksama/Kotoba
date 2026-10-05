import codecs
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import translate_json as t


class FakeClient:
    def __init__(self, transform=None):
        self.calls = 0
        self.transform = transform or (lambda text: text.replace("こんにちは", "Hello").replace("世界", "world"))

    def translate(self, text, source, target, seed=0):
        self.calls += 1
        return self.transform(text)


class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pattern = t.protected_regex([])

    def translator(self, client, **kwargs):
        result = t.Translator(client, self.root / "cache.sqlite3", self.pattern, "Japanese (ja)",
                              "English (en)", 300, 0, "test-digest", **kwargs)
        self.addCleanup(result.cache.close)
        return result

    def test_nested_json_only_values_and_exact_nontranslated_bytes(self):
        source = '{\r\n  "日本語": [9007199254740993, 1.2300, 1e+03, true, null, {"a/b~": "こんにちは"}], "stable": "\\u0041"\r\n}\r\n'
        values = t.string_values(source)
        self.assertEqual(values[0].pointer, "/日本語/5/a~1b~0")
        rendered = t.render(source, [(values[0], 'Hello "world"\n\\')])
        self.assertEqual(rendered, source.replace('"こんにちは"', json.dumps('Hello "world"\n\\', ensure_ascii=False)))
        self.assertEqual(json.loads(rendered)["日本語"][0], 9007199254740993)

    def test_root_string_and_escaped_keys(self):
        self.assertEqual(t.string_values('"こんにちは"')[0].pointer, "")
        self.assertEqual(t.string_values('{"a\\\"b":"こんにちは"}')[0].path, ('a"b',))

    def test_invalid_and_duplicate_key_json_rejected(self):
        for text in ['{"a":1,"a":2}', '{"n":NaN}', '[Infinity]', '{"a":1,}']:
            with self.subTest(text=text), self.assertRaises((t.TranslationError, ValueError)):
                t.string_values(text)

    def test_control_codes_survive_and_quotes_are_serialized(self):
        text = '  こんにちは、{player}！\\C[2]%1$s\\C[0]<b>世界</b>\r\n\t  '
        translated = self.translator(FakeClient()).translate(text)
        self.assertEqual(translated, text.replace("こんにちは", "Hello").replace("世界", "world"))
        self.assertEqual(self.pattern.findall(translated), self.pattern.findall(text))

    def test_control_code_removal_duplication_reordering_rejected(self):
        masked, saved, regex = t.mask("こんにちは {player} %d", self.pattern)
        first, second = [item[0] for item in saved]
        for output in [masked.replace(first, ""), masked + first, masked.replace(first, "TEMP").replace(second, first).replace("TEMP", second)]:
            with self.subTest(output=output), self.assertRaises(t.TranslationError):
                t.restore(output, saved, regex, self.pattern, "こんにちは {player} %d")

    def test_extra_control_codes_rejected(self):
        with self.assertRaises(t.TranslationError):
            self.translator(FakeClient(lambda text: "Hello %s")).translate("こんにちは")

    def test_segmented_fallback_and_cached_review_flag(self):
        def transform(text):
            if "ZXQ" in text:
                return "Hello world"
            return text.replace("こんにちは", "Hello").replace("世界", "world")
        translator = self.translator(FakeClient(transform))
        self.assertEqual(translator.translate("こんにちは{player}世界"), "Hello{player}world")
        self.assertTrue(translator.last_segmented)
        self.assertEqual(translator.translate("こんにちは{player}世界"), "Hello{player}world")
        self.assertTrue(translator.last_segmented)
        self.assertEqual(translator.hits, 1)

    def test_strict_tokens_disables_segmented_fallback(self):
        translator = self.translator(FakeClient(lambda text: "Hello"), strict_tokens=True)
        with self.assertRaises(t.ProtectedTokenError):
            translator.translate("こんにちは{player}")

    def test_mask_marker_collision(self):
        text = "こんにちは ZXQ0000QXZ {player}"
        masked, saved, regex = t.mask(text, self.pattern)
        self.assertNotEqual(saved[0][0], "ZXQ0000QXZ")
        self.assertEqual(t.restore(masked, saved, regex, self.pattern, text), text)

    def test_chunking_is_lossless_and_does_not_cut_codes(self):
        text = "こんにちは。" * 100 + "\\V[123]" + "世界" * 200
        pieces = t.chunks(text, self.pattern, 100)
        self.assertEqual("".join(pieces), text)
        self.assertTrue(all(len(piece.encode("utf-8")) <= 750 for piece in pieces))
        self.assertTrue(any("\\V[123]" in piece for piece in pieces))

    def test_custom_codes_are_preserved(self):
        pattern = t.protected_regex([r"\[wait=\d+\]"])
        masked, saved, regex = t.mask("こんにちは[wait=20]", pattern)
        self.assertEqual(t.restore(masked.replace("こんにちは", "Hello"), saved, regex, pattern, "こんにちは[wait=20]"), "Hello[wait=20]")

    def test_cache_resume_does_not_call_model(self):
        client = FakeClient()
        translator = self.translator(client)
        self.assertEqual(translator.translate("こんにちは"), "Hello")
        translator.cache.close()
        resumed = self.translator(client)
        self.assertEqual(resumed.translate("こんにちは"), "Hello")
        self.assertEqual(client.calls, 1)
        self.assertEqual(resumed.hits, 1)

    def test_failed_translation_not_cached(self):
        client = FakeClient(lambda text: text)
        translator = self.translator(client)
        with self.assertRaises(t.TranslationError):
            translator.translate("こんにちは")
        self.assertEqual(translator.cache.execute("SELECT count(*) FROM translations").fetchone()[0], 0)

    def test_boms_and_crlf_preserved(self):
        for encoding, bom in [("utf-8", codecs.BOM_UTF8), ("utf-16-le", codecs.BOM_UTF16_LE), ("utf-32-be", codecs.BOM_UTF32_BE)]:
            with self.subTest(encoding=encoding):
                path = self.root / "source.json"
                raw = bom + '{\r\n"a":"こんにちは"\r\n}'.encode(encoding)
                path.write_bytes(raw)
                text, found_encoding, found_bom = t.decode_file(path)
                self.assertEqual(found_encoding, encoding)
                self.assertEqual(found_bom + text.encode(found_encoding), raw)

    def test_no_overwrite_and_output_backup(self):
        output = self.root / "out.json"
        t.write_result(output, b"original")
        with self.assertRaises(t.TranslationError):
            t.write_result(output, b"new")
        t.write_result(output, b"new", overwrite=True)
        self.assertEqual(output.read_bytes(), b"new")
        self.assertEqual(next(self.root.glob("*.bak-*")).read_bytes(), b"original")

    def test_filters_skip_technical_subtrees(self):
        args = t.arguments(["input.json", "--include", "/dialogues/*/text", "--exclude", "/dialogues/1/*"])
        items = t.string_values('{"path":"画像.png","dialogues":[{"text":"こんにちは"},{"text":"世界"}]}')
        self.assertEqual([i.pointer for i in items if t.selected(i, args, self.pattern)], ["/dialogues/0/text"])
        args = t.arguments(["input.json"])
        item = t.StringValue(0, 1, "こんにちは", ("script", 0))
        self.assertFalse(t.selected(item, args, self.pattern))

    def test_dry_run_no_network_or_writes(self):
        source = self.root / "source.json"
        source.write_text('{"text":"こんにちは"}', encoding="utf-8")
        with patch.object(t.Ollama, "request", side_effect=AssertionError("network")), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(t.run([str(source), "--dry-run"]), 0)
        self.assertEqual(list(self.root.iterdir()), [source])

    def test_source_cannot_be_output_even_with_overwrite(self):
        source = self.root / "source.json"
        source.write_text('"こんにちは"', encoding="utf-8")
        with self.assertRaises(t.TranslationError):
            t.run([str(source), "-o", str(source), "--overwrite"])
        self.assertEqual(source.read_text(encoding="utf-8"), '"こんにちは"')

    def test_truncated_generation_rejected(self):
        client = t.Ollama("http://127.0.0.1:11434", "fake")
        with patch.object(client, "request", return_value={"done": True, "done_reason": "length", "response": "partial"}):
            with self.assertRaises(t.TranslationError):
                client.translate("こんにちは", "Japanese (ja)", "English (en)")

    def test_glossary_works_offline_and_does_not_change_unselected_values(self):
        source, output, glossary = self.root / "in.json", self.root / "out.json", self.root / "glossary.json"
        source.write_text('{"text":"こんにちは","path":"こんにちは"}', encoding="utf-8")
        glossary.write_text('{"こんにちは":"Hello"}', encoding="utf-8")
        with patch.object(t.Ollama, "request", side_effect=AssertionError("network")), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(t.run([str(source), "-o", str(output), "--glossary", str(glossary)]), 0)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), {"text": "Hello", "path": "こんにちは"})

    def test_glossary_cannot_change_protected_codes(self):
        source, glossary = self.root / "in.json", self.root / "glossary.json"
        source.write_text('"こんにちは{player}"', encoding="utf-8")
        glossary.write_text('{"こんにちは{player}":"Hello"}', encoding="utf-8")
        with self.assertRaises(t.TranslationError):
            t.run([str(source), "--glossary", str(glossary)])

    def test_directory_traversal_preserves_layout_and_nontext_files(self):
        source, output = self.root / "source", self.root / "translated"
        (source / "nested").mkdir(parents=True)
        (source / "first.json").write_bytes(b'{"value": 1.2300}')
        (source / "nested" / "second.json").write_bytes(b'[true,null,9007199254740993]')
        (source / "untouched.txt").write_bytes(b"not JSON")
        with patch.object(t.Ollama, "request", side_effect=AssertionError("network")), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(t.run([str(source), "-o", str(output)]), 0)
        self.assertEqual((output / "first.json").read_bytes(), (source / "first.json").read_bytes())
        self.assertEqual((output / "nested" / "second.json").read_bytes(), (source / "nested" / "second.json").read_bytes())
        self.assertFalse((output / "untouched.txt").exists())

    def test_failure_leaves_source_and_output_untouched(self):
        source, output = self.root / "source.json", self.root / "out.json"
        source.write_text('{"text":"こんにちは"}', encoding="utf-8")
        original = source.read_bytes()
        with patch.object(t.Ollama, "model_digest", return_value="digest"), patch.object(t.Ollama, "translate", side_effect=t.TranslationError("truncated")), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = t.run([str(source), "-o", str(output), "--cache", str(self.root / "cache.db"), "--retries", "0"])
        self.assertEqual(code, 1)
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
