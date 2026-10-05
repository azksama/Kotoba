"""Astra RPG Maker exports: only translation values may change."""
import fnmatch
import json
import re
from dataclasses import replace
from pathlib import Path

import translate_json as t

MARKER = re.compile(r"⟦ASTRA_[A-Za-z0-9_]+⟧")


def run_astra(args, document):
    target = 'fr' if args.target.startswith('French') else 'en' if args.target.startswith('English') else None
    if document.get('targetLanguage') != target:
        raise t.TranslationError('La langue choisie ne correspond pas à cet export Astra. Sélectionnez la langue indiquée par targetLanguage dans le fichier.')
    if document.get('version') != 1 or not isinstance(document.get('entries'), list):
        raise t.TranslationError('Unsupported Astra export version or entries')
    source = args.input.resolve()
    output = (args.output or source.with_name(source.stem + '.translated.json')).resolve()
    occupied = {source, output}
    if source == output or (output.exists() and output.samefile(source)):
        raise t.TranslationError('Output must be separate from the input')
    if args.cache.resolve() in occupied or (args.report and (args.report.resolve() in occupied or args.report.resolve() == args.cache.resolve() or args.report.exists())):
        raise t.TranslationError('Cache/report paths must be separate and report must be new')
    if output.exists() and not args.overwrite and not args.dry_run:
        raise t.TranslationError('Output already exists')
    text, encoding, bom = t.decode_file(source)
    spans = {v.path: v for v in t.string_values(text)}
    pattern = t.protected_regex([MARKER.pattern, *args.protect_regex])
    selected = []
    groups = {}
    for i, entry in enumerate(document['entries']):
        if not isinstance(entry, dict) or not isinstance(entry.get('source'), str) or not isinstance(entry.get('translation'), str):
            raise t.TranslationError(f'Invalid Astra entry {i}')
        tokens = entry.get('protectedTokens', [])
        if not isinstance(tokens, list) or any(not isinstance(x, dict) or not isinstance(x.get('marker'), str) for x in tokens):
            raise t.TranslationError(f'Invalid Astra protected tokens at {i}')
        if MARKER.findall(entry['source']) != [x['marker'] for x in tokens]:
            raise t.TranslationError(f'Astra marker mismatch at entry {i}')
        group = entry.get('identityGroup')
        if group:
            if not isinstance(group, str): raise t.TranslationError('Invalid identity group')
            members = groups.setdefault(group, [])
            members.append(i)
        span = replace(spans[('entries', i, 'translation')], value=entry['source'])
        if args.include and not any(fnmatch.fnmatchcase(span.pointer, p) for p in args.include): continue
        if any(fnmatch.fnmatchcase(span.pointer, p) for p in args.exclude): continue
        if not entry['translation'] and entry['source'].strip(): selected.append((i, span))
    # Logical identities must stay consistent, including entries outside a filter.
    preserved = set()
    for members in groups.values():
        if any(document['entries'][i].get('preserveOriginal') for i in members): preserved.update(members)
        sources = {document['entries'][i]['source'] for i in members}
        existing = {document['entries'][i]['translation'] for i in members if document['entries'][i]['translation']}
        if len(sources) != 1 or len(existing) > 1:
            raise t.TranslationError('Inconsistent Astra identity group')
    print(f'1 file(s), {len(selected)} string(s) selected', flush=True)
    if args.dry_run:
        for _, span in selected: print(f'{source.name}  {span.pointer}  {json.dumps(span.value[:100], ensure_ascii=False)}')
        return 0
    glossary = t.strict_loads(t.decode_file(args.glossary)[0]) if args.glossary else {}
    if not isinstance(glossary, dict) or any(not isinstance(v, str) or not v.strip() for v in glossary.values()):
        raise t.TranslationError('Invalid glossary')
    client = t.Ollama(args.host, args.model, args.timeout)
    translators = {}
    report = {'version': t.VERSION, 'format': 'astra-rpgm-translation', 'files': [], 'errors': [], 'review': [], 'glossary_hits': 0}
    replacements = []
    identities = {g: next((document['entries'][i]['translation'] for i in members if document['entries'][i]['translation']), None) for g, members in groups.items()}
    digest = None
    try:
        for count, (i, span) in enumerate(selected, 1):
            entry = document['entries'][i]; original = span.value
            markers = MARKER.findall(original)
            canonical = original
            for n, marker in enumerate(markers): canonical = canonical.replace(marker, f'⟦ASTRA_LOCAL_{n}⟧')
            group = entry.get('identityGroup')
            review = None
            try:
                if entry.get('preserveOriginal') or i in preserved:
                    translated = original
                elif group and identities.get(group):
                    translated = identities[group]
                elif original in glossary:
                    translated = glossary[original]; report['glossary_hits'] += 1
                elif not t.JAPANESE.search(pattern.sub('', original)) and not args.all_strings:
                    translated = original
                else:
                    keyed = bool(markers)
                    if keyed not in translators:
                        if digest is None: digest = client.model_digest()
                        args.cache.parent.mkdir(parents=True, exist_ok=True)
                        translators[keyed] = t.Translator(client, args.cache, pattern if keyed else t.protected_regex(args.protect_regex), args.source, args.target, args.chunk_chars, args.retries, digest, args.all_strings, args.strict_tokens)
                    worker = translators[keyed]
                    translated = worker.translate(canonical)
                    for n, marker in enumerate(markers): translated = translated.replace(f'⟦ASTRA_LOCAL_{n}⟧', marker)
                    if worker.last_segmented: review = 'Translated in fragments; review fluency'
                if pattern.findall(translated) != pattern.findall(original):
                    raise t.ProtectedTokenError('Astra protected tokens changed')
                if group: identities[group] = translated
            except t.ProtectedTokenError as exc:
                if args.strict_tokens: raise
                translated = ''
                review = f'Untranslated: {exc}. Empty translation keeps the original in Astra.'
            if review:
                report['review'].append({'path': span.pointer, 'reason': review})
                print(f'REVIEW {source.name} {span.pointer}: {review}', flush=True)
            replacements.append((span, translated))
            print(f'[{count}/{len(selected)}] {source.name} {span.pointer}', flush=True)
        rendered = t.render(text, replacements)
        check = t.strict_loads(rendered)
        for before, after in zip(document['entries'], check['entries']):
            if {k:v for k,v in before.items() if k != 'translation'} != {k:v for k,v in after.items() if k != 'translation'}:
                raise t.TranslationError('Astra metadata changed')
        t.write_result(output, bom + rendered.encode(encoding), args.overwrite)
        report['files'].append({'input':str(source),'output':str(output),'translated':len(replacements)})
    except t.TranslationError as exc:
        report['errors'].append({'error':str(exc)})
        print(f'ERROR {source}: {exc}', file=t.sys.stderr, flush=True)
    finally:
        report.update(api_calls=client.calls, cache_hits=sum(w.hits for w in translators.values()))
        for worker in translators.values(): worker.cache.close()
    if args.report: t.write_result(args.report, json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8'))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report['errors'] else 0
