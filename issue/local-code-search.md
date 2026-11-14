# Local code search for the sandboxed Claude

Research summary. Requirements: local only (no cloud embeddings or
vector DBs), runs inside the container, persistent file-based index
inside the project dir (gitignored), updated on request, gives Claude
code-aware retrieval and analysis.

Researched 2026-11-14 from project READMEs via web search. Release
dates and star counts were not always visible; re-check maintenance and
licence before adopting. Nothing here was installed or benchmarked by
us.

## Candidates

| Tool | Parse | Search | Embeddings | Index | Deps | Licence |
|---|---|---|---|---|---|---|
| [Semble](https://github.com/MinishLab/semble) | tree-sitter chunks | BM25 + vector, RRF, rerank | static Model2Vec (potion-code-16M-v2), CPU, no torch/ONNX | OS cache dir, `SEMBLE_CACHE_LOCATION` overrides | Python (uv/PyPI) | MIT |
| [cocoindex-code](https://github.com/cocoindex-io/cocoindex-code) | AST, ~35 langs | vector, single `search` tool | snowflake-arctic-embed-xs via sentence-transformers | `<project>/.cocoindex_code/` (LMDB + SQLite) | `[full]` adds ~1 GB torch | Apache-2.0 |
| [Serena](https://github.com/oraios/serena) | LSP, 40+ langs | symbols, references, rename, symbolic edits | none | not documented | one language server per language | GPL-3.0 app, MIT SolidLSP |
| [Srclight](https://github.com/srclight/srclight) | tree-sitter, call graph | 3x FTS5, symbols, impact, git blame/hotspots | optional, Ollama only (Voyage is cloud: avoid) | `.srclight/index.db` (SQLite) | Python 3.11+ | MIT |
| [anyindex-mcp](https://github.com/officialalexeev/anyindex-mcp) | tree-sitter | BM25 + vector, RRF | jina-embeddings-v2-base-code q8, ~157 MB, ONNX | `.anyindex/index.db` (SQLite) | Node 22+ | MIT |
| [code-rag-mcp](https://github.com/de4er00/code-rag-mcp) | Python `ast` only; rest by lines | BM25 + dense, optional reranker | bge-small via fastembed | single SQLite | Python | MIT |
| [claude-context-local](https://github.com/FarhanAliRaza/claude-context-local) | AST/tree-sitter, 9+ langs | FAISS vector | embeddinggemma-300m, ~1.2 GB | `~/.claude_code_search` (configurable) | Python 3.12+ | GPL-3.0 |

Rejected: Zilliz claude-context (Milvus + OpenAI by default) and
Code-Index-MCP (semantic search configured with a Voyage API key): both
cloud-dependent. Zoekt/Sourcegraph: no agent-ready local MCP found in
research; heavy for this use.

Complements, not competitors: `ripgrep`, `ctags`, and `ast-grep`
(structural patterns) for exact and syntactic queries.

## Findings

- **Semble** is the best fit for "efficient + persistent + simple".
  Reported: NDCG@10 0.855 over ~1,250 queries / 63 repos, ~500 ms
  average indexing, ~1 ms queries, mtime-based incremental refresh,
  `search` and `find_related` MCP tools, no GPU/torch. Claims are the
  author's own benchmark. Model downloads from Hugging Face on first
  use (or load from a local path), so pre-fetch it once.
- **Retrieval vs analysis are different tools.** Embedding/hybrid
  search answers "where is X handled"; it does not give references,
  call graphs or types. Serena (LSP) or Srclight (tree-sitter call
  graph, name-based, approximate) cover that.
- **Weight matters.** cocoindex-code `[full]` (~1 GB torch) and
  claude-context-local (~1.2 GB model) are heavy for per-session
  installs. Semble and code-rag-mcp are light.
- **Maturity is uneven.** anyindex-mcp and code-rag-mcp are tiny
  (0 stars, ~11-13 commits); anyindex's own benchmark shows quality
  dropping on larger repos (top-3 0.711 Flask vs 0.328 Fastify).
  Srclight has 235 commits but small adoption and inconsistent docs.
- **Licences:** Serena's app is GPL-3.0; claude-context-local is
  GPL-3.0. Running them as separate MCP processes is not linking, but
  check this is acceptable before bundling them in an image.

## Recommended architecture

In the container, stdio MCP servers, no host component (the host MCP
adds token/port surface and platform-specific wheels).

1. **Primary: Semble** as the search layer.
   - Install per session via `rootfs/opt/installer/semble` (no root,
     under `~/.local`), matching the `mongodb` installer pattern.
   - Index: `SEMBLE_CACHE_LOCATION=/project/.claude-index/<uname -sm>/`
     (per-platform key, per CLAUDE.md sandbox/host rule). Add
     `.claude-index/` to `.gitignore`.
   - Model: cache under `~/.cache/claude-podman/` and mount in, or
     bake into the image, so sessions don't redownload.
   - "Updated by request": Semble refreshes by mtime in MCP mode;
     `semble clear` forces a rebuild. Expose via a documented command
     or flag (`claude-podman --reindex`) rather than a watcher.
2. **Optional second layer: structure/analysis**, only if Claude
   needs references or call graphs:
   - Serena for Python (pyright/jedi LSP) and other LSP languages, if
     the GPL is acceptable; or
   - Srclight with embeddings off (FTS5 + call graph only), single
     SQLite in `.srclight/`, no Ollama needed.
3. **Always available:** `ripgrep`, `ctags`, `ast-grep` in the base
   image for exact/structural queries.
4. **Wire-up:** register the MCP server(s) in the session MCP config
   (session dir, not the repo) and add a line to `sandbox-rules.md`
   telling Claude to prefer the index for broad questions and `rg` for
   exact strings.

## Open questions

- Is a 1-2 s first-use model download acceptable, or must the image
  ship the model (offline-ready)?
- Is the GPL for Serena acceptable, or do we start with Semble alone
  and add Srclight only if reference/call-graph queries prove needed?
- Which languages must be covered first (decides LSP servers needed)?

## Next step

Spike: install Semble in a scratch container, point
`SEMBLE_CACHE_LOCATION` at a per-platform dir, index this repo and one
larger repo, and compare against `rg` on ~20 real questions before
writing an installer.
