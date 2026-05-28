# Phase 7 Wave-0 Probe Findings

**Probed:** 2026-05-05
**Probed by:** Plan 07-01 Task 1

## graphifyy 0.7.5 API

Version installed: `0.7.5` (via `importlib.metadata.version('graphifyy')` — `graphify.__version__` is unset, returns `unknown`).

### Module surfaces

```json
{
  "detect": [
    "CODE_EXTENSIONS", "CORPUS_UPPER_THRESHOLD", "CORPUS_WARN_THRESHOLD",
    "DOC_EXTENSIONS", "Enum", "FILE_COUNT_UPPER", "FileType",
    "IMAGE_EXTENSIONS", "OFFICE_EXTENSIONS", "PAPER_EXTENSIONS", "Path",
    "VIDEO_EXTENSIONS", "annotations", "classify_file",
    "convert_office_file", "count_words", "detect", "detect_incremental",
    "docx_to_markdown", "extract_pdf_text", "fnmatch", "json",
    "load_manifest", "os", "re", "save_manifest",
    "xlsx_extract_structure", "xlsx_to_markdown"
  ],
  "build": [
    "Path", "annotations", "build", "build_from_json", "build_merge",
    "deduplicate_by_label", "json", "nx", "re", "sys", "validate_extraction"
  ],
  "cluster": [
    "annotations", "cluster", "cohesion_score", "contextlib", "inspect",
    "io", "nx", "score_all", "sys"
  ],
  "analyze": [
    "CODE_EXTENSIONS", "DOC_EXTENSIONS", "IMAGE_EXTENSIONS",
    "PAPER_EXTENSIONS", "Path", "annotations", "god_nodes", "graph_diff",
    "nx", "suggest_questions", "surprising_connections"
  ],
  "report": ["annotations", "date", "generate", "nx", "re"],
  "export": [
    "COMMUNITY_COLORS", "Counter", "MAX_NODES_FOR_VIZ", "Path",
    "annotations", "attach_hyperedges", "generate_html", "json",
    "json_graph", "math", "nx", "prune_dangling_edges", "push_to_neo4j",
    "re", "sanitize_label", "to_canvas", "to_cypher", "to_graphml",
    "to_html", "to_json", "to_obsidian", "to_svg"
  ],
  "extract": [
    "Any", "Callable", "LanguageConfig", "Path", "annotations",
    "collect_files", "dataclass", "extract", "extract_blade",
    "extract_c", "extract_cpp", "extract_csharp", "extract_dart",
    "extract_elixir", "extract_fortran", "extract_go", "extract_java",
    "extract_js", "extract_julia", "extract_kotlin", "extract_lua",
    "extract_objc", "extract_php", "extract_powershell", "extract_python",
    "extract_ruby", "extract_rust", "extract_scala", "extract_sql",
    "extract_svelte", "extract_swift", "extract_verilog", "extract_zig",
    "field", "importlib", "json", "load_cached", "os", "re",
    "save_cached", "sys"
  ],
  "cache": [
    "Path", "annotations", "cache_dir", "cached_files",
    "check_semantic_cache", "clear_cache", "file_hash", "hashlib",
    "json", "load_cached", "os", "save_cached", "save_semantic_cache",
    "tempfile"
  ]
}
```

### v4 SKILL.md function signatures in 0.7.5

```json
{
  "graphify.detect.detect": "(root: 'Path', *, follow_symlinks: 'bool' = False) -> 'dict'",
  "graphify.build.build_from_json": "(extraction: 'dict', *, directed: 'bool' = False) -> 'nx.Graph'",
  "graphify.cluster.cluster": "(G: 'nx.Graph') -> 'dict[int, list[str]]'",
  "graphify.cluster.score_all": "(G: 'nx.Graph', communities: 'dict[int, list[str]]') -> 'dict[int, float]'",
  "graphify.analyze.god_nodes": "(G: 'nx.Graph', top_n: 'int' = 10) -> 'list[dict]'",
  "graphify.analyze.surprising_connections": "(G: 'nx.Graph', communities: 'dict[int, list[str]] | None' = None, top_n: 'int' = 5) -> 'list[dict]'",
  "graphify.analyze.suggest_questions": "(G: 'nx.Graph', communities: 'dict[int, list[str]]', community_labels: 'dict[int, str]', top_n: 'int' = 7) -> 'list[dict]'",
  "graphify.report.generate": "(G: 'nx.Graph', communities: 'dict[int, list[str]]', cohesion_scores: 'dict[int, float]', community_labels: 'dict[int, str]', god_node_list: 'list[dict]', surprise_list: 'list[dict]', detection_result: 'dict', token_cost: 'dict', root: 'str', suggested_questions: 'list[dict] | None' = None, min_community_size: 'int' = 3, built_at_commit: 'str | None' = None) -> 'str'",
  "graphify.export.to_json": "(G: 'nx.Graph', communities: 'dict[int, list[str]]', output_path: 'str', *, force: 'bool' = False, built_at_commit: 'str | None' = None) -> 'bool'",
  "graphify.export.to_html": "(G: 'nx.Graph', communities: 'dict[int, list[str]]', output_path: 'str', community_labels: 'dict[int, str] | None' = None, member_counts: 'dict[int, int] | None' = None, node_limit: 'int | None' = None) -> 'None'"
}
```

### DRIFT vs SKILL.md v4 (RESEARCH §Pitfall 4)

- detect: PRESENT — signature: `(root: 'Path', *, follow_symlinks: 'bool' = False) -> 'dict'`
- build_from_json: PRESENT — signature: `(extraction: 'dict', *, directed: 'bool' = False) -> 'nx.Graph'`
- cluster: PRESENT — signature: `(G: 'nx.Graph') -> 'dict[int, list[str]]'`
- score_all: PRESENT — signature: `(G: 'nx.Graph', communities: 'dict[int, list[str]]') -> 'dict[int, float]'`
- god_nodes: PRESENT — signature: `(G: 'nx.Graph', top_n: 'int' = 10) -> 'list[dict]'`
- surprising_connections: PRESENT — signature: `(G: 'nx.Graph', communities: 'dict[int, list[str]] | None' = None, top_n: 'int' = 5) -> 'list[dict]'`
- suggest_questions: PRESENT — signature: `(G: 'nx.Graph', communities: 'dict[int, list[str]]', community_labels: 'dict[int, str]', top_n: 'int' = 7) -> 'list[dict]'`
- report.generate: PRESENT — signature: `(G, communities, cohesion_scores, community_labels, god_node_list, surprise_list, detection_result, token_cost, root, suggested_questions=None, min_community_size=3, built_at_commit=None) -> str`
- export.to_json: PRESENT — signature: `(G, communities, output_path, *, force=False, built_at_commit=None) -> bool`
- export.to_html: PRESENT — signature: `(G, communities, output_path, community_labels=None, member_counts=None, node_limit=None) -> None`

**Conclusion:** All 10 v4 SKILL.md symbols are PRESENT in 0.7.5. No DRIFT detected at the symbol-name level.

**Notable signature observations for Plan 03:**

- `report.generate` requires **community_labels** (dict[int, str]) — Plan 03 must derive labels (e.g., from largest tickers/sectors per community) since cluster() returns only indexed communities. SKILL.md v4 implies an extra step here.
- `export.to_json` returns `bool` (not None) and accepts `force` keyword + optional `built_at_commit`. Plan 03 should pass repo HEAD short-hash for traceability.
- `export.to_html` receives `community_labels` AND `member_counts` (dict[int, int]) — Plan 03 derives both from cluster output.
- `analyze.suggest_questions` requires `community_labels` (not optional). Plan 03 chains: cluster → derive labels → score_all → god_nodes → surprising_connections → suggest_questions → generate.
- `detect.detect` returns `dict` (manifest); Plan 03 stages a windowed vault dir first, then calls detect on staging root.
- `extract` module exists but only as language-specific code extractors (extract_python etc.). For markdown vault our pipeline uses build_from_json directly (Claude Schedule produces extraction dicts upstream), per RESEARCH guidance.

### Plan 03 directive

If any required symbol is MISSING, Plan 03 Task 1 MUST adapt: either swap to the
0.7.5 equivalent (document mapping here) or pin graphifyy to an older version that
has the v4 surface. Do NOT silently drop functionality.

→ **No remediation needed. All symbols PRESENT.** Plan 03 proceeds with v4 chain
unchanged. Plan 03 Task 1 must, however, derive `community_labels` and
`member_counts` itself (graphifyy does not auto-generate these).

## DART supersedes frontmatter field

### Code grep results

```
$ grep -nE "correction|정정|rcept_no_origin|amendment|supersedes|기재정정" \
    src/collectors/dart/ src/shared/frontmatter.py
(no matches)
```

The DART writer (`src/collectors/dart/writer.py`) writes only:
- `provenance.{source, source_id, source_url, content_hash, fetched_at, lang, ticker, corp_code, company_name, date, trust_level}`
- `ingest_state.{injection_flags, processed}`
- (optionally) `_derived` block populated downstream by Claude Schedule

**No correction/amendment/supersedes/rcept_no_origin field is written or referenced anywhere in the DART collector or shared frontmatter schema.**

### Sample vault frontmatter (top 2 DART filings)

```yaml
# vault/raw/dart/2026/20260318001062_00126380.md
ingest_state:
  injection_flags: []
  processed: false
provenance:
  company_name: 삼성전자
  content_hash: 8b4b2f773f65aab8e7aaaacadfb2acd60508c06c945d809e549d927eb9faa71d
  corp_code: 00126380
  date: '2026-03-18'
  fetched_at: 2026-04-25 00:49:23.298277+00:00
  lang: ko
  source: dart
  source_id: '20260318001062'
  source_url: https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260318001062
  ticker: 005930
  trust_level: trusted

# vault/raw/dart/2026/20260318001203_00126380.md
ingest_state:
  injection_flags: []
  processed: false
provenance:
  company_name: 삼성전자
  content_hash: 9931c141f36e0a954a65f736d8ab5c90ba12cb0655706cb62afedf2b246ccbf2
  corp_code: 00126380
  date: '2026-03-18'
  ...
```

No correction marker present in any sampled DART filing.

### Conclusion

**MISSING: no DART filing in current vault carries any correction marker.**

Plan 02 Task 2 supersedes derivation MUST then write a placeholder that returns
`counters['supersedes_skipped_no_field']=N` (or similar) and document this gap
in `07-01-SUMMARY.md` for a follow-up quick task to extend
`src/collectors/dart/writer.py` to surface DART's 기재정정 (correction) marker.

The dart-fss `Report` object surface (probed below) does not expose a
correction-source field either, so the upstream collector must be enhanced to
either (a) parse the report title for `[기재정정]` prefix and the embedded
"정정 대상 보고서" fields, or (b) call OpenDART's `notice_search` with
`pblntf_detail_ty='I001'` to fetch correction relationships separately. This
work is OUT OF SCOPE for Phase 7 Plan 02 — it's filed as a deferred quick task
that, when implemented, will populate `provenance.correction_of_rcept_no` (or
chosen field name) which `_derive_supersedes` already-knows how to read.

## DART filing object (dart-fss) fields

dart-fss version: `0.4.15`

The class formerly imported in plans as `dart_fss.filings.filing.Filing` does
**not exist** in 0.4.15 — `ModuleNotFoundError: No module named
'dart_fss.filings.filing'`. The current filing-like surfaces are:

```
dart_fss.filings.search_result.SearchResults
  attrs: ['page_count', 'page_no', 'pop', 'report_list', 'to_dict',
          'total_count', 'total_page']

dart_fss.filings.reports.Report
  attrs: ['attached_files', 'attached_reports', 'extract_attached_files',
          'extract_attached_reports', 'extract_pages', 'extract_related_reports',
          'extract_xbrlviewer', 'find_all', 'load', 'load_xbrl', 'pages',
          'rcept_no', 'related_reports', 'to_dict', 'xbrl', 'xbrlviewer']
```

Correction-hint scan: `[x for x in dir(Report) if any(k in x.lower() for k in
['correct','rcept','origin','amend','super'])]` → `['rcept_no']` only.

**Any field hinting at correction (e.g. `rcept_no_origin`, `correction_of`)?
N — only `rcept_no` (the current report's own number) is exposed.**

The `related_reports` attribute may surface chains of related filings, but its
semantics (does it include corrections? supersedes targets? earnings revisions?)
are not documented in dart-fss 0.4.15 and require empirical verification. For
Phase 7 Plan 02, treat as MISSING.
