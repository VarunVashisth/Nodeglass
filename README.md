# Nodeglass

A local Electron application for exploring source dependencies, statically resolved calls, and function statements. Python, JavaScript, TypeScript, and TSX are parsed with their own Tree-sitter grammars. Analysis is stored in SQLite; repository code is read, never imported or executed.

## Install and run

Requires Python 3.12+, Node.js 22+, npm, and a graphical desktop. Run from the repository root:

```sh
uv sync --locked
npm --prefix frontend ci
npm --prefix frontend run dev
```

Electron starts the Python backend automatically using `.venv/bin/python` (`.venv/Scripts/python.exe` on Windows), waits for its authenticated health check, and terminates it when the app closes. Set `NODEGLASS_PYTHON` to use another Python executable. If npm blocks Electron's installation script, explicitly install its runtime:

```sh
cd frontend
node node_modules/electron/install.js
```

Without uv, create a Python virtual environment and install `backend/requirements.txt` with pip. The uv and npm lockfiles provide the preferred reproducible installation.

Select **Open repository**, choose `fixtures/example`, and wait for analysis. Dependencies show `main.py → auth.py` and `main.py → database.py`. Switch to **Call graph**, select `login`, and choose **Downstream**. It calls `get_user` and conditionally calls `authenticate`. The inspector shows parameters, callers, callees, reference locations, and read-only source. **View function flow** shows assignments, branches, returns, and basic value dependencies.

Files expand into symbols in the explorer. The Entries tab lists verified registrations and script guards. Graphs support pan, zoom, draggable nodes, fit, LR/TB auto-layout, relationship selection, connected-node emphasis, child collapse/expand, bounded upstream/downstream traversal, and reset. Depth is limited to 10 and graph responses to 500 nodes (200 by default).

## Separate backend for development

The launch token is required, including for `/health`. Use the same token in both terminals; do not commit it. Example for POSIX shells:

```sh
export NODEGLASS_TOKEN="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export NODEGLASS_PORT=8765
uv run python -m backend.entry
```

In another terminal, set `NODEGLASS_TOKEN` to that generated value:

```sh
export NODEGLASS_BACKEND_URL=http://127.0.0.1:8765
npm --prefix frontend run dev
```

The backend binds to `127.0.0.1`. Without `NODEGLASS_PORT`, it reserves an available port and emits a JSON handshake containing only the port and protocol version. The token travels through the child environment and authenticated requests. Default development origin: `http://127.0.0.1:5173`. Packaged origin: `nodeglass://app`.

Database location is Electron's OS user-data directory. Standalone default is `~/.local/share/Nodeglass/analysis.sqlite3`; override with `NODEGLASS_DATA_DIR`. The frontend accesses the database only through HTTP.

## Checks

```sh
uv run pytest
npm --prefix frontend run typecheck
npm --prefix frontend run build
uv run python scripts/smoke_backend.py
```

The desktop smoke test uses a real Electron renderer and backend, substituting only the native folder dialog. Start `npm --prefix frontend run dev:web` in another terminal, then:

```sh
npm --prefix frontend run test:e2e
```

For a preinstalled Electron executable, set `NODEGLASS_ELECTRON_EXECUTABLE` when running the smoke test. Screenshots are written to `frontend/test-results/`. Test runners need permission to communicate over loopback; restricted environments may prevent the FastAPI test client's cross-thread event loop from starting.

## Build the desktop application

Build on the intended OS; cross-platform binaries and signing are not supplied.

```sh
uv run python scripts/package_backend.py
uv run python scripts/smoke_backend.py --packaged
npm --prefix frontend run package
```

PyInstaller collects the Python app, SQLAlchemy, Uvicorn, and grammar extension packages into `dist/nodeglass-backend`. Electron Builder places this directory in the application's resources and creates an unpacked app in `frontend/release`. Run `npm --prefix frontend run dist` for an OS-specific installer (AppImage, DMG, or NSIS). Installer signing/notarization requires your own credentials and platform tools.

The executable backend and unpacked Electron 45 Linux application have been built and smoke-tested. The packaged app passed folder opening, analysis, all three graph views, the inspector, rescan, authenticated API communication, and backend shutdown checks. The test substitutes only the native folder dialog selection. Other operating systems and signed installers have not been tested.

Run the built Linux application directly with `frontend/release/linux-unpacked/nodeglass-desktop`.

## Analysis model and guarantees

- Tree-sitter byte offsets remain byte offsets. Locations store one-based lines and zero-based UTF-8 byte columns. Preview decoding happens only after source ranges have been extracted.
- Separate extraction, resolution, persistence, and graph construction modules live in `backend/app/services`. A small normalized relational entity table holds symbols, imports, references, calls, assignments, returns, controls, hooks, and lexical scopes. Repository/file/scope/target links use indexed columns and foreign keys; syntax details use JSON.
- IDs hash repository identity, relative file path, entity kind, source byte position, and name. Unchanged scans preserve IDs; moving a declaration or changing preceding source can change them. Repository registrations are local to each database and selected path; IDs are not portable across machines.
- Each scan runs on one bounded background worker. A transaction replaces changed file entities, removes deleted files, and reruns resolution across the entire repository before committing. Content hashes avoid reparsing unchanged files. Readers see the last committed scan.
- Python resolution supports lexical functions/parameters/bindings, local absolute and relative modules, import aliases, class ownership, and straightforward `self.method()` or direct-constructor receiver calls. JavaScript/TypeScript support relative imports, named/default exports, aliases, namespace imports, common index files, arrow functions, and block scopes for let/const.
- Imports to missing relative modules remain unresolved. Nonlocal packages are external. Unknown receivers/callables, duplicate definitions, and unsupported expressions remain unresolved or ambiguous. A same-named symbol in another file is insufficient to resolve a call.
- Calls point from caller to callee; imports point from importing file to dependency. Call-site arguments, locations, conditional controls, and resolution status travel with edges. Recursive/cyclic paths use existing nodes and bounded visited-set traversal.
- Function flow is a syntax-level approximation. `CONTAINS` links identify statements and enclosing constructs; `CONTROL_FLOW` marks possible entry into a construct, not sequential execution order. `RETURNS` points from a return statement to its function. `DATA_DEPENDS_ON` points from an assignment to a referenced definition and is explicitly inferred. Distinct branches are never joined into a fabricated sequential trace.
- FastAPI/APIRouter decorators and Express route registrations require recognizable imported constructors. Unverified method-name matches are retained as candidates internally and excluded from the entry-point graph. Script guards are possible entry points, never evidence of execution.
- Default generated-directory exclusions and nested `.gitignore` rules apply. Symlinks are skipped. Unsupported files retain metadata without fabricated symbols. Supported source files with invalid UTF-8, binary content, parser errors, or excessive size are reported. Maximum file size is 2 MiB.

## MVP limitations

This is static analysis, not a compiler, debugger, runtime tracer, or proof of runtime order.

- No full TypeScript module resolver, tsconfig aliases, package exports, CommonJS `require`, re-export chains, Python star-import expansion, or installed-package inspection.
- No general type inference, dynamic dispatch, inherited-method lookup, monkey patching, computed property resolution, Python global/nonlocal semantics, comprehensions as scopes, JS catch/loop initializer scopes, or overload selection. Complex callable/receiver expressions are retained unresolved; branch-dependent assignments are approximations.
- Parameter declarations/defaults/annotations are preserved as source strings. Decorator/default-expression references, class fields, and every language-specific declaration form are not exhaustively modeled.
- HTTP hook support covers recognizable direct FastAPI/APIRouter and Express construction. Router inclusion/prefix composition, lifespans/startup registration, inline Express callbacks, and arbitrary event-emitter types are not fully resolved.
- Flow is scoped to one function; it has basic assignment dependencies and control containment, not a complete CFG, SSA, argument propagation, or interprocedural data-flow engine. Await/yield constructs are stored but do not imply conditional execution by themselves.
- Source preview has line numbers and lightweight token coloring, not a complete editor or language server. It refuses stale previews until a rescan.
- Symbol search returns at most 500 items by default (API limit 2,000). Graph rendering is bounded, but backend graph construction and repository-wide resolution still read the repository's extracted entities into memory. Target small/medium repositories.
- There is no migration system yet. Future schema changes require a migration or recreation of the local analysis database. There is no scan cancellation, file watcher, analysis history, or multi-user service.

The original experiments in `backend/parsers` are preserved and are not used by the application or collected as tests.
