# Project: Local Code Intelligence & Execution Flow Visualizer

## 1. Objective

Build a minimal, production-quality desktop application that can analyze a local source-code repository, extract structured information using Tree-sitter, persist that information in SQLite, and visualize relationships between files, symbols, functions, classes, and possible execution paths as an interactive directed graph.

The application should help developers understand:

- How files and modules depend on each other.
- Where functions, methods, classes, and variables are defined.
- Where symbols are referenced.
- Which functions call other functions.
- How data may flow through assignments, arguments, and return statements.
- How execution can travel through different files.
- Which functions are triggered by external entry points, such as HTTP routes.
- How control-flow constructs affect possible execution paths.

This is the first version of a larger codebase-understanding system.

**Primary requirement:** Build a small, clean, maintainable foundation with working end-to-end functionality. Avoid unnecessary abstraction, excessive files, premature optimization, and unrelated features.

Do not build an AI chatbot, LLM integration, RAG pipeline, vector database, or cloud service.

---

# 2. Technology Stack

## Frontend

Use:

- Electron — desktop application shell.
- React — UI framework.
- TypeScript — type safety.
- Vite — development and build tooling.
- Tailwind CSS — styling.
- React Flow (`@xyflow/react`) — interactive directed graph.
- Dagre (`@dagrejs/dagre`) — automatic graph layout.
- Lucide React — icons.
- Zustand — minimal shared application state.
- TanStack Query — API request and cache management.

Use native browser APIs wherever possible.

Avoid adding a large component library unless absolutely necessary.

## Backend

Use:

- Python 3.12+
- FastAPI
- Uvicorn
- Tree-sitter and required language grammar packages
- SQLAlchemy 2.x
- SQLite
- Pydantic
- pytest

Use synchronous SQLAlchemy sessions initially for simplicity.

Do not introduce Redis, Celery, PostgreSQL, Docker, message brokers, or microservices.

## Architecture

Electron launches and manages a local FastAPI backend.

React communicates with FastAPI over HTTP on `127.0.0.1`.

The application must work locally without an internet connection after dependencies are installed.

The frontend must never access the SQLite database directly.

---

# 3. Project Structure

Keep the structure conventional, minimal, and easy to navigate.

```text
project/
├── frontend/
│   ├── electron/
│   │   ├── main.ts
│   │   └── preload.ts
│   ├── src/
│   │   ├── components/
│   │   │   ├── graph/
│   │   │   └── layout/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── services/
│   │   ├── store/
│   │   ├── types/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
│
├── backend/
│   ├── app/
│   │   ├── db/
│   │   │   ├── database.py
│   │   │   └── models.py
│   │   ├── routes/
│   │   │   ├── projects.py
│   │   │   └── graph.py
│   │   ├── services/
│   │   │   ├── parser.py
│   │   │   ├── extractor.py
│   │   │   ├── resolver.py
│   │   │   └── graph_builder.py
│   │   ├── middleware/
│   │   ├── schemas.py
│   │   ├── config.py
│   │   └── main.py
│   ├── tests/
│   ├── requirements.txt
│   └── entry.py
│
├── README.md
└── .gitignore
```

This is a suggested structure, not a requirement to create empty files.

Only create modules when they have actual responsibilities.

Do not split small, closely related functions across unnecessary files.

Responsibilities:

- `parser.py`: Tree-sitter language detection, parsing, and syntax tree access.
- `extractor.py`: Extract syntax-level information from AST nodes.
- `resolver.py`: Resolve imports, scopes, definitions, references, and call targets.
- `graph_builder.py`: Convert persisted analysis into graph nodes and edges.
- `models.py`: SQLAlchemy database entities.
- `schemas.py`: Pydantic request and response schemas.
- `routes/`: HTTP API endpoints.
- `middleware/`: Only middleware genuinely required for security or request handling.

Keep the implementation modular enough to extend later without introducing a plugin architecture now.

---

# 4. Language Support

Design the parser to support multiple languages, but initially implement and thoroughly test:

1. Python
2. JavaScript
3. TypeScript

Support TSX if the selected Tree-sitter grammar is available.

Each language must use the appropriate Tree-sitter grammar and extraction rules.

Do not assume all languages use the same AST node names or symbol-resolution semantics.

Use a language-specific extraction strategy behind a shared normalized output schema.

For unsupported languages:

- Record the file as unsupported.
- Do not crash repository analysis.
- Do not fabricate extracted symbols.

Keep the design extensible for C, C++, Java, Rust, and Go later, but do not implement them now.

---

# 5. Repository Scanning

The user should be able to select a local repository folder through Electron's native folder-selection dialog.

The frontend sends the selected path to the backend through a controlled, validated IPC/API workflow.

The backend recursively discovers supported source files.

## File metadata

Extract and store:

- Repository-relative path.
- Language.
- Content SHA-256 hash.
- File size.
- Last modified timestamp.
- Parsing status.
- Parsing errors, if any.

Use the content hash to detect changes.

Ignore common irrelevant directories:

```text
.git/
node_modules/
.venv/
venv/
__pycache__/
dist/
build/
coverage/
.next/
```

Also respect `.gitignore` rules where practical.

Avoid following symbolic links outside the selected repository.

Handle unreadable files, binary files, and unsupported encodings gracefully.

Use repository-relative paths in persisted graph identities rather than absolute machine-specific paths.

For MVP, support one active repository at a time while allowing the database to identify repositories separately.

---

# 6. Tree-sitter Parsing

Use Tree-sitter as the foundation for syntactic analysis.

For every supported source file:

1. Detect the programming language.
2. Read the source as bytes.
3. Initialize the appropriate Tree-sitter parser.
4. Parse the source into a syntax tree.
5. Traverse relevant named AST nodes.
6. Extract normalized entities.
7. Store source ranges and relationships.
8. Record syntax errors without failing the entire repository.

Tree-sitter byte offsets must be handled correctly.

Store both byte ranges and human-readable line/column locations where appropriate.

Do not confuse UTF-8 byte offsets with character offsets.

## Parsing constraints

- Do not use regex as the primary method for parsing code.
- Do not extract symbols from raw text when a Tree-sitter node is available.
- Do not assume every identifier reference can be resolved.
- Preserve unresolved references for later inspection.
- Do not silently discard parser errors.

For initial repository rescans, reparse only changed files using content hashes.

Full Tree-sitter incremental editing through `tree.edit()` can be added later; it is not required for this MVP.

---

# 7. Required Information Extraction

Extract the following categories.

## 7.1 Files

Store:

- Repository-relative path.
- Language.
- Content hash.
- File metadata.
- Parse status.

Purpose: Identify source files, support dependency mapping, and detect changes.

## 7.2 Imports

Extract:

- Importing file.
- Module path or import source.
- Imported symbol names.
- Aliases.
- Relative import level, where applicable.
- Source location.
- Resolved target file/module, if determinable.

Examples:

```python
from services.auth import validate_user as check_user
```

```typescript
import { validateUser as checkUser } from "./auth";
```

Create dependency relationships when the imported module resolves to a local repository file.

Distinguish internal modules from external packages.

Do not create fictional local files for external dependencies.

## 7.3 Functions and Methods

Extract:

- Name.
- Qualified name.
- Parameters.
- Parameter defaults, where present.
- Type annotations.
- Return annotation.
- Enclosing scope.
- Containing class, if any.
- Async/sync status.
- Decorators.
- Source location.
- Function body range.

Example:

```python
class UserService:
    def authenticate(self, username: str) -> bool:
        return True
```

Identify:

```text
UserService.authenticate
```

as a method belonging to `UserService`.

Qualified names must account for nested functions and classes.

## 7.4 Classes

Extract:

- Name.
- Qualified name.
- Base classes.
- Defined methods.
- Enclosing scope.
- Decorators, if applicable.
- Source location.

Create class-to-method ownership relationships.

Create inheritance relationships only when the base class can be resolved with sufficient confidence.

Otherwise preserve the base-class expression as unresolved.

## 7.5 Definitions and References

Extract:

- Symbol name.
- Definition location.
- Reference locations.
- Symbol kind.
- Scope.
- Resolved definition ID, when available.

Support lexical scope resolution.

Distinguish:

- Local variables.
- Function parameters.
- Functions.
- Classes.
- Imported symbols.
- Module-level bindings.
- Class members when resolvable.

Do not link two identifiers solely because their text matches.

For unresolved or ambiguous references, retain their status instead of inventing a relationship.

## 7.6 Function Calls

Extract:

- Callee expression.
- Argument expressions.
- Keyword/named arguments where supported.
- Enclosing function or module scope.
- Source location.
- Resolved target symbol, when possible.

Example:

```python
def main():
    result = process_data(10)
    return result
```

Create:

```text
main -> process_data
```

when the target is resolved.

For:

```python
service.process_data()
```

attempt to resolve the receiver and method through available static information.

If the receiver type is unknown, preserve an unresolved call.

Do not claim complete runtime call resolution.

## 7.7 Assignments

Extract:

- Assignment target.
- Value expression.
- Enclosing scope.
- Source location.
- Operator type, when applicable.

Examples:

```python
result = calculate_total(price, quantity)
```

```python
a = b
```

Represent the assignment and its possible value dependencies.

Handle destructuring and multiple assignments at least at the syntax-extraction level.

Do not implement a full compiler-grade data-flow engine.

## 7.8 Return Statements

Extract:

- Returned expression.
- Enclosing function.
- Source location.

Example:

```python
def calculate():
    result = process()
    return result
```

Record the relationship between the return expression and its enclosing function.

Use this information for a basic function-level data-flow view.

## 7.9 Control Constructs

Extract:

- Conditional branches.
- Loops.
- Exception handling.
- `await` expressions.
- `yield` expressions.
- Break and continue statements.
- Relevant source locations.
- Enclosing function.

Support language-specific equivalents.

For example:

```python
def process(value):
    if value > 10:
        return high(value)
    else:
        return low(value)
```

Preserve the condition and branch structure.

Represent possible paths, not guaranteed runtime paths.

Do not attempt exhaustive symbolic execution.

## 7.10 Framework Hooks

Extract externally triggered execution entry points.

Initial supported cases:

### Python / FastAPI

Detect common patterns such as:

```python
@app.get("/users")
def get_users():
    return service.get_users()
```

```python
@router.post("/login")
async def login():
    return authenticate()
```

Extract:

- HTTP method.
- Route path.
- Handler function.
- Decorator location.
- Router ownership, if resolvable.

Also recognize common startup/lifespan registration patterns where practical.

### JavaScript / TypeScript

Recognize common Express-style patterns:

```typescript
app.get("/users", getUsers);
```

Extract route registrations when the receiver and handler are sufficiently identifiable.

### Event handlers

Record identifiable event registrations and callbacks.

Unknown frameworks should not produce fabricated framework metadata.

Keep framework detection rule-based and extensible.

---

# 8. Normalized Analysis Model

Design a normalized internal representation independent of Tree-sitter's language-specific AST node names.

At minimum, represent:

```text
Repository
SourceFile
Symbol
Import
Reference
CallSite
Assignment
ReturnStatement
ControlConstruct
FrameworkHook
```

Each extracted entity should have:

- Stable identifier.
- Owning repository.
- Owning file.
- Entity type.
- Name or expression.
- Source range.
- Enclosing scope.
- Relevant structured metadata.
- Resolution status where applicable.

Use explicit fields for commonly queried relationships.

A JSON metadata field may be used for language-specific details, but must not replace essential relational structure.

## Stable identities

Graph and database IDs must remain stable across unchanged scans.

Use deterministic identities based on repository, file, entity kind, and suitable source/scope identity.

Handle duplicate names and overloaded/nested symbols.

Do not rely on the symbol name alone as a unique ID.

For the MVP, IDs may change when a declaration is moved or its structural identity changes. Document this limitation.

---

# 9. Symbol and Dependency Resolution

After extraction, run a separate resolution pass.

The resolver should:

1. Build symbol tables for each scope.
2. Resolve local lexical references.
3. Resolve supported relative imports.
4. Resolve supported absolute imports within the repository.
5. Link imported names to exported definitions when possible.
6. Resolve direct function calls.
7. Resolve class ownership.
8. Resolve straightforward method calls when receiver identity is statically known.
9. Preserve unresolved and ambiguous relationships.

## Resolution states

Use explicit statuses:

```text
resolved
ambiguous
unresolved
external
```

For graph edges, distinguish confirmed static relationships from inferred ones.

Do not label a relationship as confirmed merely because a similarly named function exists.

## Cross-file resolution

Example:

```python
# main.py
from services.user import get_user

def run():
    return get_user()
```

```python
# services/user.py
def get_user():
    return {"id": 1}
```

Expected:

```text
main.py
  -> services/user.py

run()
  -> get_user()
```

The call relationship must point to the actual resolved definition.

For JavaScript and TypeScript, implement common local module resolution patterns, including relative imports and supported index files.

Do not attempt to reproduce the entire TypeScript compiler resolution system in the MVP.

---

# 10. Graph Construction

Build a directed, typed, multi-level graph from persisted analysis.

Do not construct the graph directly from raw Tree-sitter nodes in the frontend.

The backend owns graph semantics.

## Graph node types

Support:

```text
file
module
function
method
class
variable
parameter
control
entry_point
external
unresolved
```

Not every extracted statement must appear as a graph node in every view.

## Graph edge types

Support:

```text
IMPORTS
DEFINES
CONTAINS
INHERITS
REFERENCES
CALLS
ASSIGNS
RETURNS
DATA_DEPENDS_ON
CONTROL_FLOW
TRIGGERS
```

Every edge must have a clear direction and semantic meaning.

For example:

```text
Function A --CALLS--> Function B
```

means Function A contains a statically identified call to Function B.

Do not reverse the direction merely for visual layout.

Store source location, resolution status, and relevant metadata on edges.

## Important graph distinction

Implement three logical graph views:

### A. Dependency Graph

Shows:

- Files/modules.
- Import relationships.
- Internal dependencies.

### B. Call / Execution Graph

Shows:

- Functions.
- Methods.
- Entry points.
- Caller-to-callee relationships.
- Potential execution paths.

This is a static approximation of possible execution, not a runtime trace.

### C. Data / Control Flow Graph

Shows selected function-level details:

- Assignments.
- Value dependencies.
- Return statements.
- Conditions.
- Branches.
- Loops.

For the MVP, keep this view scoped to a selected function.

Avoid generating a full interprocedural data-flow graph.

Use a simple, documented static approximation and mark uncertain relationships.

## Graph expansion

Support progressive exploration:

```text
Repository
   |
   v
File
   |
   v
Function
   |
   v
Called Function
   |
   v
Return / Further Calls
```

The user should be able to move from a high-level file graph into more detailed symbol relationships.

Avoid displaying thousands of AST nodes simultaneously.

---

# 11. Execution Flow Traversal

Implement directed traversal of the resolved call graph.

Example:

```python
# main.py
from auth import authenticate
from database import get_user

def login(username, password):
    user = get_user(username)

    if user:
        return authenticate(user, password)

    return False
```

Expected call graph:

```text
login()
   |
   +----> get_user()
   |
   +----> authenticate()
```

The graph must not falsely imply that `authenticate()` always executes.

Use conditional edge or call-site metadata to indicate that the call is inside a branch.

## Required traversal capabilities

- Find direct callees.
- Find direct callers.
- Traverse downstream calls.
- Traverse upstream callers.
- Limit traversal depth.
- Detect cycles.
- Avoid infinite recursion.
- Highlight a selected path.
- Display unresolved call sites.

If a function is called recursively, represent the cycle without endlessly duplicating nodes.

If multiple possible paths exist, show them as possibilities.

Do not claim the graph is a real runtime execution trace.

---

# 12. SQLite Database

Use SQLAlchemy 2.x ORM.

SQLite is the only database required.

Use a small relational schema that can persist:

- Repositories.
- Source files.
- Symbols and scopes.
- Imports.
- References.
- Calls.
- Assignments.
- Returns.
- Control constructs.
- Framework hooks.
- Graph relationships or enough normalized data to derive them.

Avoid creating a separate database table for every AST node type if a simpler normalized design is sufficient.

Use foreign keys and indexes for commonly queried relationships.

Enable SQLite foreign-key enforcement.

Use WAL mode where appropriate.

Store the database in the application's user-data directory, not inside the source repository.

## Re-analysis

On subsequent scans:

1. Compare current file hashes.
2. Skip unchanged files.
3. Re-extract changed files.
4. Remove entities belonging to deleted files.
5. Re-resolve relationships affected by changes.
6. Prevent duplicate symbols and edges.
7. Persist the new consistent analysis state.

Do not merely re-resolve changed files: other files may import or reference them.

Use transactions to avoid leaving partially replaced analysis data.

For the MVP, it is acceptable to rerun repository-wide resolution after selectively reparsing changed files.

---

# 13. FastAPI Endpoints

Implement a small REST API.

Suggested endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Backend health |
| POST | `/api/projects/open` | Register selected repository |
| POST | `/api/projects/{id}/scan` | Analyze or rescan repository |
| GET | `/api/projects/{id}/files` | List analyzed files |
| GET | `/api/projects/{id}/symbols` | Search/list symbols |
| GET | `/api/projects/{id}/graph` | Get graph by view and filters |
| GET | `/api/projects/{id}/functions/{symbol_id}/flow` | Function-level flow |
| GET | `/api/projects/{id}/execution` | Traverse possible call paths |

Use query parameters for:

- Graph view.
- Starting node.
- Traversal direction.
- Maximum depth.
- Edge types.
- Node limits.

## API response format

Use a consistent graph response:

```json
{
  "nodes": [
    {
      "id": "function:main.py:run",
      "type": "function",
      "label": "run()",
      "file": "main.py",
      "metadata": {}
    }
  ],
  "edges": [
    {
      "id": "call:main.py:run:1",
      "source": "function:main.py:run",
      "target": "function:services/user.py:get_user",
      "type": "CALLS",
      "resolution": "resolved",
      "metadata": {}
    }
  ]
}
```

This is an illustrative schema, not a mandate to use name-only IDs.

Actual IDs must follow the stable identity rules.

Use Pydantic response models and validate request parameters.

Use appropriate HTTP status codes.

Handle large repositories and malformed requests gracefully.

Repository scanning must not block the API event loop.

Use a bounded worker or background execution strategy suitable for a single-user desktop application.

---

# 14. Electron Integration and Security

Electron is responsible for:

- Opening the desktop window.
- Showing the native folder picker.
- Starting the Python backend.
- Monitoring backend health.
- Shutting down the backend when Electron exits.
- Exposing a minimal safe IPC bridge.

## Electron security

Require:

```typescript
webPreferences: {
  contextIsolation: true,
  nodeIntegration: false,
  sandbox: true,
  preload: preloadPath
}
```

Expose only necessary APIs through `contextBridge`.

Do not expose unrestricted filesystem or Node.js access to React.

Do not disable web security.

## Backend lifecycle

For development:

- Support a separately launched Python backend.
- Electron should be able to connect to it through an explicit development configuration.

For production:

- Electron should launch the packaged Python backend.
- Bind only to `127.0.0.1`.
- Prefer an OS-assigned available port.
- Communicate the chosen port to Electron through a controlled startup handshake.
- Generate a per-launch authentication token.
- Require authentication on application API requests.
- Do not log or expose the token.
- Restrict CORS to the expected application origin.
- Terminate the backend when the desktop application closes.
- Prevent arbitrary websites from invoking local backend functionality.

Treat repository source code as untrusted input.

Never execute imported repository code to perform static analysis.

Do not run arbitrary shell commands from source files.

Do not follow untrusted navigation requests in Electron.

## Packaging

Set up a minimal reproducible packaging workflow for the frontend and Python backend.

Ensure the packaged application can locate its backend, Tree-sitter grammars, and database directory.

Document the packaging method and test it where the environment permits.

Do not claim production packaging works unless it has been tested.

---

# 15. Frontend UI / UX

Build a minimal, professional developer-tool interface.

The design should feel like a modern code intelligence tool rather than an administrative dashboard.

Use:

- Dark-first theme.
- Neutral backgrounds.
- Subtle borders.
- Clear typography.
- Consistent spacing.
- Restrained accent colors.
- Minimal animations.
- Compact but readable information density.

Avoid unnecessary cards, large decorative headers, gradients, and excessive visual effects.

## Main application layout

```text
┌──────────────────────────────────────────────────────┐
│ Project Name      Search              Scan   Settings│
├──────────────┬────────────────────────┬──────────────┤
│              │                        │              │
│ EXPLORER     │      GRAPH CANVAS      │ INSPECTOR    │
│              │                        │              │
│ Files        │    [Function A]        │ Selected     │
│ Symbols      │          │             │ Node         │
│ Entry Points │          ▼             │              │
│              │    [Function B]        │ Details      │
│              │          │             │ References   │
│              │          ▼             │ Callers      │
│              │    [Function C]        │ Callees      │
│              │                        │              │
├──────────────┴────────────────────────┴──────────────┤
│ Status: Analysis Complete | Files: 42 | Symbols: 280 │
└──────────────────────────────────────────────────────┘
```

Use resizable panels if practical.

Do not add a complicated docking system.

## 15.1 Project Explorer

Left sidebar:

- Repository file tree.
- Symbol search.
- Entry-point list.
- File selection.
- Expandable functions/classes.

Selecting a file should update the graph.

## 15.2 Graph Canvas

Use React Flow.

Required:

- Pan.
- Zoom.
- Fit to view.
- Auto-layout.
- Directed arrows.
- Node selection.
- Edge selection.
- Highlight connected relationships.
- Expand/collapse exploration.
- Graph view switching.
- Zoom controls.
- Mini-map only if useful.
- Clear loading and empty states.

Use Dagre for automatic layout.

Support left-to-right and top-to-bottom layout options.

## 15.3 Node Appearance

Use distinct, subtle visual styles for:

- Files.
- Functions.
- Methods.
- Classes.
- Entry points.
- Variables.
- Control nodes.
- Unresolved symbols.

Node labels should be concise.

Show additional details in the inspector rather than overcrowding graph nodes.

## 15.4 Edge Appearance

Edges must have visible arrowheads.

Distinguish relationships using restrained colors, line styles, or labels.

Examples:

- Imports: dashed.
- Calls: solid.
- Data dependency: dotted.
- Control flow: directed.
- Unresolved relationship: muted.

Provide a small graph legend.

Ensure edge direction remains understandable at different zoom levels.

## 15.5 Inspector Panel

When a node is selected, display:

- Name.
- Type.
- Qualified name.
- File path.
- Source location.
- Parameters.
- Return annotation.
- Parent scope.
- Callers.
- Callees.
- References.
- Resolution status.

Only display fields relevant to the selected node type.

For a call edge, show:

- Caller.
- Callee.
- Call-site location.
- Arguments.
- Resolution confidence/status.
- Whether the call is conditional.

Provide an action to focus the graph on a related symbol.

## 15.6 Execution Exploration

When a function is selected, provide:

- Explore downstream calls.
- Explore upstream callers.
- View function flow.
- Set traversal depth.
- Reset graph focus.

Highlight possible execution paths.

Do not animate fake execution or imply that static analysis proves runtime order.

## 15.7 Source Preview

Provide a lightweight read-only source preview for the selected symbol.

Show a small relevant code snippet with line numbers.

Use a lightweight syntax-highlighting solution.

Do not add a full code editor or language server.

Source preview must not execute code.

## 15.8 Analysis Progress

During repository scanning, show:

- Current status.
- Number of files discovered.
- Number of files parsed.
- Number of files skipped.
- Errors encountered.

A basic progress indicator is sufficient.

Avoid introducing WebSockets unless required.

Simple polling is acceptable.

---

# 16. Performance Requirements

The UI must remain responsive during analysis and graph rendering.

Requirements:

- Avoid reparsing unchanged files.
- Batch database writes.
- Use indexes for common graph queries.
- Limit graph expansion depth.
- Apply node-count limits.
- Avoid rendering the entire repository at once.
- Cache graph responses where useful.
- Cancel or ignore stale frontend requests.
- Show a clear warning when a graph exceeds the visualization limit.

Use progressive graph exploration rather than loading everything into React Flow.

Target small-to-medium repositories initially.

Do not introduce distributed processing or a complex job queue.

---

# 17. Error Handling

Handle:

- Invalid repository paths.
- Permission errors.
- Unsupported languages.
- Invalid UTF-8 sequences.
- Tree-sitter syntax errors.
- Unresolved imports.
- Ambiguous symbols.
- Cyclic imports.
- Recursive function calls.
- Deleted files.
- Backend startup failure.
- Database errors.
- Oversized graph responses.

Errors must not silently disappear.

Show actionable error messages in the frontend.

A failure in one source file should not necessarily terminate the entire repository scan.

---

# 18. Testing

Implement automated tests for the core analysis engine.

## Parser tests

Verify:

- Python function extraction.
- JavaScript/TypeScript function extraction.
- Class extraction.
- Nested functions.
- Parameters and annotations.
- Imports and aliases.
- Calls.
- Assignments.
- Returns.
- Control constructs.
- Framework hooks.

## Resolution tests

Verify:

- Local function calls.
- Cross-file imports.
- Aliased imports.
- Nested lexical scopes.
- Duplicate symbol names.
- Unresolved references.
- Ambiguous method calls.
- Cyclic imports.

## Graph tests

Verify:

- Correct node IDs.
- Correct edge direction.
- Caller/callee relationships.
- Dependency relationships.
- Recursive call cycles.
- Traversal depth limits.
- Conditional-call metadata.

## Database tests

Verify:

- Initial scan.
- Rescan without changes.
- Modified file.
- Deleted file.
- Cross-file relationship updates.
- No duplicate persisted entities.

## API tests

Verify:

- Health endpoint.
- Project opening.
- Scan operation.
- Graph retrieval.
- Invalid requests.
- Authentication behavior.

Use small fixture repositories rather than huge external projects.

---

# 19. Acceptance Test: End-to-End Example

Create a fixture repository:

```text
example/
├── main.py
├── auth.py
└── database.py
```

`main.py`:

```python
from auth import authenticate
from database import get_user

def login(username, password):
    user = get_user(username)

    if user:
        return authenticate(user, password)

    return False

def main():
    return login("admin", "1234")

if __name__ == "__main__":
    main()
```

`auth.py`:

```python
def authenticate(user, password):
    return user["password"] == password
```

`database.py`:

```python
def get_user(username):
    return {
        "username": username,
        "password": "1234"
    }
```

Expected dependency graph:

```text
main.py
   ├──> auth.py
   └──> database.py
```

Expected call graph:

```text
main()
   |
   v
login()
   |
   ├──> get_user()
   |
   └──> authenticate()
```

The call to `authenticate()` must be marked as conditional.

The `if __name__ == "__main__"` construct should be recognized as a possible script entry-point guard, without assuming the script was actually executed.

Expected behavior:

1. User opens the example folder.
2. Backend scans the three files.
3. Tree-sitter extracts their entities.
4. Resolver links the cross-file imports and calls.
5. SQLite persists the results.
6. Frontend displays the file dependency graph.
7. User selects `main()`.
8. Frontend displays downstream call relationships.
9. User selects `login()`.
10. Inspector shows parameters, file location, callers, and callees.
11. User switches to function flow view.
12. Conditional branch and return information are displayed.
13. Rescanning without changes does not duplicate data.

This scenario must work end to end.

---

# 20. Implementation Order

Implement in the following order.

### Phase 1 — Project Foundation

- Create frontend and backend structure.
- Configure React, Vite, Electron, and Tailwind.
- Configure FastAPI and SQLAlchemy.
- Implement local backend communication.
- Create basic application layout.

### Phase 2 — Parser and Extraction

- Implement file discovery.
- Implement language detection.
- Integrate Tree-sitter.
- Implement language-specific extraction.
- Normalize extracted entities.
- Add extraction tests.

### Phase 3 — Persistence and Resolution

- Design database models.
- Persist extracted entities.
- Implement lexical scope resolution.
- Implement import resolution.
- Implement direct call resolution.
- Add incremental file-hash rescanning.
- Add resolution and database tests.

### Phase 4 — Graph Engine

- Implement typed graph construction.
- Implement dependency graph.
- Implement call graph.
- Implement function-level flow graph.
- Implement traversal and cycle handling.
- Expose graph APIs.
- Add graph tests.

### Phase 5 — Frontend Visualization

- Build repository explorer.
- Integrate React Flow.
- Implement automatic layout.
- Implement node/edge styling.
- Implement graph view switching.
- Implement inspector panel.
- Implement source preview.
- Implement traversal controls.

### Phase 6 — Integration and Validation

- Test complete workflow.
- Test backend lifecycle.
- Test API authentication.
- Verify repository scanning.
- Verify graph direction.
- Verify cross-file calls.
- Verify rescanning behavior.
- Fix errors.
- Document setup and limitations.

---

# 21. Scope Restrictions

Do not implement:

- AI or LLM integrations.
- RAG or embeddings.
- Vector databases.
- Runtime code execution tracing.
- Debuggers.
- Full symbolic execution.
- Full compiler-grade data-flow analysis.
- Automatic code modifications.
- Git history visualization.
- Cloud synchronization.
- User accounts.
- Authentication systems for multiple users.
- Collaboration features.
- Browser extensions.
- Complex settings pages.
- Unnecessary animations.
- Excessive architectural abstractions.

Local backend request authentication is still required for security.

Prioritize correctness of extraction and relationships over the quantity of visual features.

---

# 22. Engineering Rules

Follow these rules throughout implementation:

1. Inspect the existing repository before modifying anything.
2. Reuse existing working configurations where appropriate.
3. Do not overwrite unrelated user files.
4. Keep functions focused and reasonably small.
5. Use clear naming and explicit types.
6. Avoid unnecessary dependencies.
7. Avoid circular imports.
8. Do not introduce placeholder implementations presented as completed functionality.
9. Do not create fake graph edges to make the UI look populated.
10. Never infer a call relationship from symbol-name equality alone.
11. Separate extraction, resolution, persistence, and visualization concerns.
12. Ensure graph relationships are deterministic and reproducible.
13. Preserve unresolved relationships explicitly.
14. Add tests alongside core functionality.
15. Do not silently change architectural decisions.
16. Keep source-code analysis strictly read-only.
17. Never execute the analyzed repository.
18. Avoid broad refactors unrelated to the task.
19. Run relevant tests and builds after implementation.
20. Report limitations accurately.

If an advanced feature cannot be implemented reliably within the MVP, implement a smaller correct version and document its limitations rather than creating misleading behavior.

---

# 23. Final Deliverables

Deliver a working project containing:

- Electron + React desktop frontend.
- FastAPI backend.
- Tree-sitter parsing for Python, JavaScript, and TypeScript.
- Normalized information extraction.
- SQLAlchemy + SQLite persistence.
- Import and symbol resolution.
- Directed dependency graph.
- Directed call graph.
- Basic function-level data/control-flow graph.
- Interactive React Flow visualization.
- File explorer.
- Symbol inspector.
- Execution traversal.
- Incremental repository rescanning.
- Automated tests.
- README with development and build instructions.

The README must explain:

- How to install dependencies.
- How to start the backend.
- How to start Electron in development.
- How to run tests.
- How to build the desktop application.
- Which languages are supported.
- Which relationships are statically resolved.
- Which relationships remain unresolved or approximate.
- Known MVP limitations.

## Final Validation

Before declaring completion:

- Run backend tests.
- Run frontend type checking.
- Run frontend build.
- Verify the example repository.
- Verify API communication.
- Verify graph rendering.
- Verify graph edge directions.
- Verify that changed files trigger updated analysis.
- Verify that unchanged files do not generate duplicate records.
- Verify backend startup and shutdown.

Report:

1. What was implemented.
2. What was tested successfully.
3. What remains incomplete.
4. Known analysis limitations.
5. Exact commands to run the project.

**Final priority:** A smaller, correct, functioning code intelligence engine is more valuable than a visually impressive interface backed by inaccurate analysis.

Start by inspecting the repository, identifying any existing implementation, and creating a concise implementation plan. Then implement the phases in order, validating each layer before proceeding. Do not stop after generating scaffolding or a plan; complete the working end-to-end MVP wherever the environment permits.
