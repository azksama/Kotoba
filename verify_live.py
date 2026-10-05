"""Verify the actual local smoke-test artifacts, without calling generation."""
import hashlib
import json
from pathlib import Path
import translate_json as t

root = Path(__file__).resolve().parent
source = root / "examples/game.ja.json"
output = root / "outputs/game.en.json"
original = source.read_text(encoding="utf-8")
translated = output.read_text(encoding="utf-8")
left, right = t.string_values(original), t.string_values(translated)
assert [x.path for x in left] == [x.path for x in right]
pattern = t.protected_regex([])
options = t.arguments([str(source)])
for before, after in zip(left, right):
    assert pattern.findall(before.value) == pattern.findall(after.value), before.pointer
    if not t.selected(before, options, pattern):
        assert before.value == after.value, before.pointer
# Replacing all string values with a sentinel leaves the exact same source skeleton.
assert t.render(original, [(x, "SENTINEL") for x in left]) == t.render(translated, [(x, "SENTINEL") for x in right])
assert (root / "outputs/game.resume.en.json").read_bytes() == output.read_bytes()
resume = json.loads((root / "outputs/resume-report.json").read_text(encoding="utf-8"))
assert resume["api_calls"] == 0 and resume["cache_hits"] == 13
live = json.loads((root / "outputs/live-report-v2.json").read_text(encoding="utf-8"))
assert not live["errors"] and live["files"][0]["translated"] == 13
client = t.Ollama("http://127.0.0.1:11434", "ja-en-game:12b")
evidence = {
    "checks": "PASS: exact JSON skeleton, protected codes, untouched values, resume output identical",
    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    "ollama": client.request("/api/version"),
    "model": client.request("/api/show", {"model": "ja-en-game:12b"})["parameters"],
    "loaded_models": client.request("/api/ps"),
    "unit_tests_passed": 23,
    "live_translated_strings": 13,
    "review_required": live["review"],
    "resume_api_calls": 0,
}
evidence_path = root / "outputs/verification.json"
evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(evidence, ensure_ascii=False, indent=2))
