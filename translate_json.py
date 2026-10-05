#!/usr/bin/env python3
"""Local JSON translator. Python 3.10+, standard library only."""
from __future__ import annotations

import argparse
import codecs
from dataclasses import dataclass
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import uuid

VERSION = "1.1.0"
ROOT = Path(__file__).resolve().parent
JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff66-\uff9f]")
# Engine-specific syntax can be added with --protect-regex.
BUILTIN_PROTECTION = (
    r"\\[A-Za-z]+(?:\[[^\]\r\n]*\]|<[^>\r\n]*>)?"
    r"|\\[^\w\s]"
    r"|\$?\{[^{}\r\n]*\}"
    r"|%(?:\d+\$)?[-+#0 ']*(?:\d+|\*)?(?:\.(?:\d+|\*))?(?:hh|ll|[hlLjzt])?[diuoxXfFeEgGaAcspn%]"
    r"|%\d+"
    r"|</?[A-Za-z][^>\r\n]*>"
    r"|&(?:#[0-9]+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);"
    r"|\r\n|[\n\r\t]"
)
DEFAULT_SKIP_KEYS = ["id", "uuid", "guid", "path", "file", "filename", "url", "uri", "script", "code"]


class TranslationError(Exception):
    pass


class ProtectedTokenError(TranslationError):
    pass


def reject_constant(value):
    raise TranslationError(f"Non-standard JSON constant: {value}")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise TranslationError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def strict_loads(text):
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)


@dataclass
class StringValue:
    start: int
    end: int
    value: str
    path: tuple

    @property
    def pointer(self):
        return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in self.path)


def string_values(text):
    """Locate string VALUES, preserving source text, keys and numeric spellings."""
    strict_loads(text)
    decoder = json.JSONDecoder()
    values = []
    size = len(text)

    def whitespace(i):
        while i < size and text[i] in " \t\r\n":
            i += 1
        return i

    def visit(i, path):
        i = whitespace(i)
        if text[i] == "{":
            i = whitespace(i + 1)
            if text[i] == "}":
                return i + 1
            while True:
                key, end = decoder.raw_decode(text, i)
                i = whitespace(end)
                i = whitespace(visit(i + 1, path + (key,)))
                if text[i] == "}":
                    return i + 1
                i = whitespace(i + 1)
        elif text[i] == "[":
            i = whitespace(i + 1)
            if text[i] == "]":
                return i + 1
            index = 0
            while True:
                i = whitespace(visit(i, path + (index,)))
                if text[i] == "]":
                    return i + 1
                i = whitespace(i + 1)
                index += 1
        value, end = decoder.raw_decode(text, i)
        if isinstance(value, str):
            values.append(StringValue(i, end, value, path))
        return end

    visit(0, ())
    return values


def decode_file(path):
    raw = path.read_bytes()
    for bom, encoding in [(codecs.BOM_UTF32_LE, "utf-32-le"), (codecs.BOM_UTF32_BE, "utf-32-be"),
                          (codecs.BOM_UTF8, "utf-8"), (codecs.BOM_UTF16_LE, "utf-16-le"),
                          (codecs.BOM_UTF16_BE, "utf-16-be")]:
        if raw.startswith(bom):
            return raw[len(bom):].decode(encoding), encoding, bom
    return raw.decode("utf-8"), "utf-8", b""


def protected_regex(extra):
    for expression in extra:
        if re.compile(expression).match(""):
            raise TranslationError("A protection regex must not match empty text")
    return re.compile("|".join(f"(?:{p})" for p in [*extra, BUILTIN_PROTECTION]))


def mask(text, pattern):
    prefix = "ZXQ"
    while prefix in text:
        prefix += "X"
    saved = []

    def substitute(match):
        marker = f"{prefix}{len(saved):04d}QXZ"
        saved.append((marker, match.group(0)))
        return marker

    return pattern.sub(substitute, text), saved, re.compile(re.escape(prefix) + r"\d+QXZ")


def restore(translated, saved, marker_pattern, pattern, original):
    expected = [marker for marker, _ in saved]
    if marker_pattern.findall(translated) != expected:
        raise ProtectedTokenError("Protected tokens were removed, duplicated or reordered")
    for marker, token in saved:
        translated = translated.replace(marker, token)
    if pattern.findall(translated) != pattern.findall(original):
        raise ProtectedTokenError("Control codes changed or unexpected control codes appeared")
    return translated


def chunks(text, pattern, max_chars=300):
    """Bound UTF-8 bytes conservatively; never cut a protected span."""
    tokens = []
    cursor = 0
    for match in pattern.finditer(text):
        tokens.extend(text[cursor:match.start()])
        tokens.append(match.group(0))
        cursor = match.end()
    tokens.extend(text[cursor:])
    result, part, length, byte_count = [], [], 0, 0
    for token in tokens:
        width = len(token.encode("utf-8"))
        if part and (length + len(token) > max_chars or byte_count + width > 750):
            # Prefer a recent sentence boundary without dropping whitespace.
            boundary = next((i + 1 for i in range(len(part) - 1, max(-1, len(part) // 2 - 1), -1)
                             if part[i] in "。！？.!? \n"), len(part))
            result.append("".join(part[:boundary]))
            part = part[boundary:]
            length = sum(map(len, part))
            byte_count = sum(len(s.encode("utf-8")) for s in part)
        part.append(token)
        length += len(token)
        byte_count += width
    if part:
        result.append("".join(part))
    return result


class Ollama:
    def __init__(self, host, model, timeout=300):
        self.host, self.model, self.timeout = host.rstrip("/"), model, timeout
        # Ignore HTTP_PROXY for local requests.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.calls = 0

    def request(self, endpoint, payload=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.host + endpoint, data=data, headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                result = json.load(response)
            if "error" in result:
                raise TranslationError(result["error"])
            return result
        except (urllib.error.URLError, TimeoutError) as exc:
            raise TranslationError(f"Ollama unavailable or request failed: {exc}") from exc

    def model_digest(self):
        models = self.request("/api/tags")["models"]
        name = self.model if ":" in self.model else self.model + ":latest"
        found = next((m for m in models if m["name"] == name), None)
        if not found:
            raise TranslationError(f"Model missing: {name}. Run setup-ollama.ps1 first.")
        return found["digest"]

    def translate(self, text, source, target, seed=0):
        prompt = (f"You are a professional {source} to {target} translator. Your goal is to accurately convey "
                  f"the meaning and nuances of the original {source} text while adhering to {target} grammar, "
                  f"vocabulary, and cultural sensitivities.\nProduce only the {target} translation, without any "
                  f"additional explanations or commentary. Please translate the following {source} text into {target}:\n\n\n{text}")
        # Bytes upper-bound text tokenization; reserve generation and template overhead.
        if len(prompt.encode("utf-8")) > 1150:
            raise TranslationError("Segment exceeds safe context budget; lower --chunk-chars")
        self.calls += 1
        result = self.request("/api/generate", {
            "model": self.model, "prompt": prompt, "stream": False, "keep_alive": "5m",
            "options": {"temperature": 0, "seed": seed, "num_ctx": 2048, "num_predict": 768},
        })
        if not result.get("done") or result.get("done_reason") != "stop":
            raise TranslationError("Incomplete/truncated model output")
        translated = result.get("response", "").strip()
        if not translated or "```" in translated:
            raise TranslationError("Empty output or unexpected Markdown block")
        return translated


class Translator:
    def __init__(self, client, cache, pattern, source, target, chunk_chars, retries, digest, all_strings=False, strict_tokens=False):
        self.client, self.pattern = client, pattern
        self.source, self.target, self.chunk_chars, self.retries = source, target, chunk_chars, retries
        self.all_strings = all_strings
        self.strict_tokens = strict_tokens
        self.last_segmented = False
        self.cache = sqlite3.connect(cache)
        self.cache.execute("CREATE TABLE IF NOT EXISTS translations (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.cache.execute("CREATE TABLE IF NOT EXISTS segmented (key TEXT PRIMARY KEY)")
        self.signature = json.dumps([VERSION, digest, source, target, pattern.pattern, chunk_chars, all_strings, strict_tokens])
        self.hits = 0

    def should_translate(self, text):
        plain = self.pattern.sub("", text)
        return bool(plain.strip()) and (self.all_strings or bool(JAPANESE.search(plain)))

    def piece(self, text):
        if not self.should_translate(text):
            return text
        leading = text[:len(text) - len(text.lstrip())]
        trailing = text[len(text.rstrip()):]
        body = text.strip()
        masked, saved, marker_pattern = mask(body, self.pattern)
        if not masked:
            return text
        for attempt in range(self.retries + 1):
            try:
                translated = self.client.translate(masked, self.source, self.target, attempt)
                result = restore(translated, saved, marker_pattern, self.pattern, body)
                if not self.pattern.sub("", result).strip():
                    raise TranslationError("Translation contains only control codes")
                if result == body:
                    raise TranslationError("Model returned the original text unchanged")
                return leading + result + trailing
            except TranslationError as exc:
                if attempt == self.retries:
                    if isinstance(exc, ProtectedTokenError) and saved and not self.strict_tokens:
                        # Last resort: the model never sees the original game codes.
                        # Keep all tokens at their exact boundaries, and flag for review.
                        self.last_segmented = True
                        output, cursor = [], 0
                        for match in self.pattern.finditer(body):
                            output.append(self.piece(body[cursor:match.start()]))
                            output.append(match.group(0))
                            cursor = match.end()
                        output.append(self.piece(body[cursor:]))
                        result = leading + "".join(output) + trailing
                        if self.pattern.findall(result) != self.pattern.findall(text):
                            raise ProtectedTokenError("Segmented control-code validation failed")
                        return result
                    raise
                time.sleep(min(attempt + 1, 3))

    def translate(self, text):
        self.last_segmented = False
        key = hashlib.sha256((self.signature + "\0" + text).encode("utf-8")).hexdigest()
        cached = self.cache.execute("SELECT value FROM translations WHERE key = ?", (key,)).fetchone()
        if cached:
            result = cached[0]
            if self.pattern.findall(result) == self.pattern.findall(text):
                self.hits += 1
                self.last_segmented = self.cache.execute("SELECT 1 FROM segmented WHERE key = ?", (key,)).fetchone() is not None
                return result
        parts = chunks(text, self.pattern, self.chunk_chars)
        translated_parts = [self.piece(part) for part in parts]
        result = ""
        for index, part in enumerate(translated_parts):
            # A forced Japanese split can otherwise join two English words.
            if (index and result and part and result[-1].isascii() and part[0].isascii()
                    and result[-1].isalnum() and part[0].isalnum()
                    and not self.pattern.search(parts[index - 1][-1:] + parts[index][:1])):
                result += " "
            result += part
        if self.pattern.findall(result) != self.pattern.findall(text):
            raise TranslationError("Final control-code validation failed")
        self.cache.execute("INSERT OR REPLACE INTO translations VALUES (?, ?)", (key, result))
        if self.last_segmented:
            self.cache.execute("INSERT OR IGNORE INTO segmented VALUES (?)", (key,))
        else:
            self.cache.execute("DELETE FROM segmented WHERE key = ?", (key,))
        self.cache.commit()
        return result


def selected(item, args, pattern):
    pointer = item.pointer
    if args.include and not any(fnmatch.fnmatchcase(pointer, p) for p in args.include):
        return False
    if any(fnmatch.fnmatchcase(pointer, p) for p in args.exclude):
        return False
    # Skip whole technical subtrees, including string entries inside an array.
    if any(isinstance(key, str) and key.casefold() in args.skip_keys for key in item.path):
        return False
    plain = pattern.sub("", item.value)
    return bool(plain.strip()) and (args.all_strings or bool(JAPANESE.search(plain)))


def render(text, replacements):
    for item, value in sorted(replacements, key=lambda pair: pair[0].start, reverse=True):
        # ensure_ascii also safely represents lone surrogate escapes in existing JSON.
        ensure_ascii = "\\u" in text[item.start:item.end]
        encoded = json.dumps(value, ensure_ascii=ensure_ascii)
        text = text[:item.start] + encoded + text[item.end:]
    strict_loads(text)
    return text


def write_result(path, data, overwrite=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise TranslationError(f"Output already exists: {path}. Use --overwrite to back it up first.")
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_bytes(data)
        if path.exists():
            if not overwrite:
                raise TranslationError(f"Output was created concurrently: {path}")
            backup = path.with_name(path.name + ".bak-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
            # Copy before atomic replacement: existing output remains usable if interrupted.
            backup.write_bytes(path.read_bytes())
            temp.replace(path)
        else:
            # Exclusive atomic publication on NTFS/POSIX; never clobber a racing writer.
            os.link(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def arguments(argv=None):
    parser = argparse.ArgumentParser(description="Translate JSON string values locally, preserving JSON syntax and protected game codes.")
    parser.add_argument("input", type=Path, help="JSON file or directory (recursive)")
    parser.add_argument("-o", "--output", type=Path, help="Destination file or directory; source is never overwritten")
    parser.add_argument("--model", default="ja-en-game:12b")
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--source", default="Japanese (ja)")
    parser.add_argument("--target", default="English (en)")
    parser.add_argument("--all-strings", action="store_true", help="Translate non-Japanese strings too (use for other source languages)")
    parser.add_argument("--include", action="append", default=[], metavar="POINTER_GLOB", help="Only matching JSON pointers, e.g. /dialogues/*/text")
    parser.add_argument("--exclude", action="append", default=[], metavar="POINTER_GLOB")
    parser.add_argument("--skip-key", action="append", default=[], help="Additional technical subtree key to preserve")
    parser.add_argument("--no-default-skip-keys", action="store_true")
    parser.add_argument("--protect-regex", action="append", default=[], help="Additional engine control-code regex")
    parser.add_argument("--strict-tokens", action="store_true", help="Fail instead of translating fragments when the model alters protected tokens")
    parser.add_argument("--glossary", type=Path, help="JSON object mapping exact source strings to approved translations")
    parser.add_argument("--chunk-chars", type=int, default=300)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--cache", type=Path, default=ROOT / ".translation-cache.sqlite3")
    parser.add_argument("--report", type=Path, help="Optional NEW JSON report file")
    parser.add_argument("--dry-run", action="store_true", help="List selected paths and previews, without contacting Ollama or writing files")
    parser.add_argument("--overwrite", action="store_true", help="Back up and replace existing OUTPUTS only")
    args = parser.parse_args(argv)
    if not 20 <= args.chunk_chars <= 300 or not 0 <= args.retries <= 5 or args.timeout <= 0:
        parser.error("chunk-chars: 20..300; retries: 0..5; timeout: positive")
    if not args.source.startswith("Japanese") and not args.all_strings:
        parser.error("Use --all-strings when translating a source language other than Japanese")
    args.skip_keys = {key.casefold() for key in args.skip_key + ([] if args.no_default_skip_keys else DEFAULT_SKIP_KEYS)}
    return args


def run(argv=None):
    args = arguments(argv)
    source = args.input.resolve()
    if not source.exists():
        raise TranslationError(f"Input missing: {source}")
    directory = source.is_dir()
    destination = (args.output or (source.with_name(source.name + "-en") if directory
                                  else source.with_name(source.stem + ".en" + source.suffix))).resolve()
    if destination == source or (directory and destination.is_relative_to(source)):
        raise TranslationError("Output must be separate from the input; a destination directory cannot be inside the source")
    files = sorted(source.rglob("*.json")) if directory else [source]
    if not files:
        raise TranslationError("No JSON files found")
    pattern = protected_regex(args.protect_regex)
    glossary = {}
    if args.glossary:
        glossary = strict_loads(decode_file(args.glossary)[0])
        if not isinstance(glossary, dict) or any(not isinstance(v, str) or not v.strip() for v in glossary.values()):
            raise TranslationError("Glossary must be a JSON object with non-empty string translations")
        for original, translation in glossary.items():
            if pattern.findall(original) != pattern.findall(translation):
                raise TranslationError(f"Glossary changes protected tokens for {original!r}")
    jobs = []
    for file in files:
        if file.is_symlink():
            raise TranslationError(f"Refusing a symlink input: {file}")
        text, encoding, bom = decode_file(file)
        items = [item for item in string_values(text) if selected(item, args, pattern)]
        output = destination / file.relative_to(source) if directory else destination
        if output.resolve() == file.resolve() or (output.exists() and output.samefile(file)):
            raise TranslationError("Output resolves to the input file")
        if output.exists() and not args.overwrite and not args.dry_run:
            raise TranslationError(f"Output already exists: {output}. Use --overwrite to back it up first.")
        jobs.append((file, output, text, encoding, bom, items))
    # Protect source/output files from accidental cache/report path collisions.
    occupied = {p.resolve() for job in jobs for p in job[:2]}
    if args.glossary:
        if args.glossary.resolve() in {job[1].resolve() for job in jobs}:
            raise TranslationError("Glossary cannot be an output file")
        occupied.add(args.glossary.resolve())
    if args.cache.resolve() in occupied or (args.report and args.report.resolve() in occupied):
        raise TranslationError("Cache/report path must differ from every input and output")
    if args.report and (args.report.exists() or args.report.resolve() == args.cache.resolve()):
        raise TranslationError("Report must be a new file, separate from the cache")
    total = sum(len(job[-1]) for job in jobs)
    print(f"{len(jobs)} file(s), {total} string(s) selected", flush=True)
    if args.dry_run:
        for file, _, _, _, _, items in jobs:
            for item in items:
                preview = json.dumps(item.value[:100], ensure_ascii=False)
                print(f"{file.name}  {item.pointer or '(root)'}  {preview}")
        return 0
    translator = None
    client = Ollama(args.host, args.model, args.timeout)
    if any(item.value not in glossary for job in jobs for item in job[-1]):
        digest = client.model_digest()
        args.cache.parent.mkdir(parents=True, exist_ok=True)
        translator = Translator(client, args.cache, pattern, args.source, args.target, args.chunk_chars,
                                args.retries, digest, args.all_strings, args.strict_tokens)
    report = {"version": VERSION, "model": args.model, "files": [], "errors": [], "review": [], "glossary_hits": 0}
    count = 0
    try:
        for file, output, text, encoding, bom, items in jobs:
            replacements = []
            try:
                for item in items:
                    try:
                        from_glossary = item.value in glossary
                        if from_glossary:
                            translation = glossary[item.value]
                            report["glossary_hits"] += 1
                        else:
                            translation = translator.translate(item.value)
                    except TranslationError as exc:
                        raise TranslationError(f"{item.pointer or '(root)'}: {exc}") from exc
                    replacements.append((item, translation))
                    if not from_glossary and translator.last_segmented:
                        report["review"].append({"file": str(file), "path": item.pointer, "reason": "Translated in fragments to preserve control codes; review fluency"})
                        print(f"REVIEW {file.name} {item.pointer}: translated in fragments to preserve codes", flush=True)
                    count += 1
                    print(f"[{count}/{total}] {file.name} {item.pointer or '(root)'}", flush=True)
                translated = render(text, replacements)
                write_result(output, bom + translated.encode(encoding), args.overwrite)
                report["files"].append({"input": str(file), "output": str(output), "translated": len(items)})
            except TranslationError as exc:
                report["errors"].append({"file": str(file), "error": str(exc)})
                print(f"ERROR {file}: {exc}", file=sys.stderr, flush=True)
                break  # No partial output for the failed file. Successful cache rows survive.
    finally:
        if translator:
            translator.cache.close()
    report.update({"api_calls": client.calls, "cache_hits": translator.hits if translator else 0})
    if args.report:
        write_result(args.report, json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


def main():
    try:
        return run()
    except (TranslationError, ValueError, OSError, RecursionError, sqlite3.Error, re.error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. Completed translations remain in the cache; source untouched.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.exit(main())
