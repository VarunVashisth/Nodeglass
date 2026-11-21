import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Braces,
  ChevronRight,
  FileCode2,
  FolderOpen,
  GitBranch,
  RefreshCw,
  Search,
  X,
  Zap,
} from "lucide-react";
import { request } from "./api";
import { useStore } from "./store";
import GraphCanvas from "./GraphCanvas";
import SourceLine from "./SourceLine";
import type {
  Graph,
  GraphEdge,
  SourceFile,
  Status,
  SymbolDetail,
  SymbolInfo,
} from "./types";
const emptyGraph: Graph = { nodes: [], edges: [], truncated: false };
export default function App() {
  const s = useStore();
  const cache = useQueryClient();
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState("files");
  const [edge, setEdge] = useState<GraphEdge | null>(null);
  const [error, setError] = useState("");
  const base = s.project ? `/api/projects/${s.project.id}` : "";
  const status = useQuery({
    queryKey: ["status", s.project?.id],
    queryFn: () => request<Status>(base + "/status"),
    enabled: !!base,
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 400 : 2000,
  });
  const running = status.data?.status === "running";
  const revision = status.data?.status;
  const files = useQuery({
    queryKey: ["files", base, revision],
    queryFn: ({ signal }) => request<SourceFile[]>(base + "/files", { signal }),
    enabled: !!base && !running,
  });
  const symbols = useQuery({
    queryKey: ["symbols", base, revision, search],
    queryFn: ({ signal }) =>
      request<SymbolInfo[]>(base + "/symbols?q=" + encodeURIComponent(search), {
        signal,
      }),
    enabled: !!base && !running,
  });
  const flowStart = s.view === "flow" ? s.focus || s.selected : s.focus;
  const params = new URLSearchParams({
    view: s.view,
    depth: String(s.depth),
    direction: s.direction,
  });
  if (flowStart) params.set("start", flowStart);
  if (s.file) params.set("file_id", s.file);
  const graph = useQuery({
    queryKey: ["graph", base, revision, params.toString()],
    queryFn: ({ signal }) =>
      request<Graph>(base + "/graph?" + params, { signal }),
    enabled: !!base && !running,
  });
  const selectedSymbol =
    symbols.data?.some((x) => x.id === s.selected) ||
    graph.data?.nodes.some(
      (n) =>
        n.id === s.selected &&
        !["file", "module", "external", "unresolved"].includes(n.type),
    );
  const detail = useQuery({
    queryKey: ["detail", base, s.selected, revision],
    queryFn: ({ signal }) =>
      request<SymbolDetail>(base + "/symbols/" + s.selected, { signal }),
    enabled: !!base && !!s.selected && selectedSymbol && !running,
  });
  const scan = useMutation({
    mutationFn: () => request<Status>(base + "/scan", { method: "POST" }),
    onSuccess: (data) => {
      cache.setQueryData(["status", s.project?.id], data);
      setError("");
    },
    onError: (e) => setError(e.message),
  });
  useEffect(() => {
    if (status.data?.status === "complete")
      cache.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "status" });
  }, [status.data?.status, cache]);
  async function open() {
    try {
      if (!window.nodeglass)
        throw new Error(
          "Start the Electron desktop app to select a local repository.",
        );
      const project = await window.nodeglass.chooseRepository();
      if (project) {
        s.setProject(project);
        setError("");
        setEdge(null);
        const state = await request<Status>(
          `/api/projects/${project.id}/scan`,
          { method: "POST" },
        );
        cache.setQueryData(["status", project.id], state);
      }
    } catch (e) {
      setError(String(e));
    }
  }
  function select(id: string) {
    setEdge(null);
    s.setSelected(id);
    const file = files.data?.find((f) => f.id === id);
    if (file) {
      s.setFile(id);
      if (s.view === "dependency") s.setFocus(id);
    }
  }
  function explore(id: string, direction: "upstream" | "downstream") {
    s.setView("calls");
    s.setDirection(direction);
    s.setFocus(id);
    s.setSelected(id);
    setEdge(null);
  }
  const activeFile = files.data?.find((f) => f.id === s.selected);
  const node = graph.data?.nodes.find((n) => n.id === s.selected);
  const visibleError =
    error ||
    (status.data?.status === "error" ? status.data.message : "") ||
    files.error?.message ||
    symbols.error?.message ||
    graph.error?.message ||
    detail.error?.message ||
    status.error?.message;
  return (
    <div className="app">
      <header>
        <div className="brand">
          <GitBranch size={22} />
          <strong>nodeglass</strong>
          <span className="divider" />
          <span className="project-name">
            {s.project?.name || "No repository"}
          </span>
        </div>
        <label className="search">
          <Search size={15} />
          <input
            aria-label="Search symbols"
            placeholder="Find a symbol…"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setTab("symbols");
            }}
          />
          <kbd>⌕</kbd>
        </label>
        <button onClick={open}>
          <FolderOpen size={15} />
          Open folder
        </button>
        <button
          className="primary"
          disabled={!s.project || running || scan.isPending}
          onClick={() => scan.mutate()}
        >
          <RefreshCw size={14} className={running ? "spin" : ""} />
          {running ? "Analyzing…" : "Scan"}
        </button>
      </header>
      {visibleError && (
        <div className="error-banner">
          {visibleError}
          <button onClick={() => setError("")} aria-label="Dismiss error">
            <X size={14} />
          </button>
        </div>
      )}
      <main>
        <aside className="explorer">
          <div className="panel-title">
            EXPLORER <span>{files.data?.length || 0} files</span>
          </div>
          <nav>
            {["files", "symbols", "entries"].map((t) => (
              <button
                key={t}
                className={tab === t ? "active" : ""}
                onClick={() => setTab(t)}
              >
                {t}
              </button>
            ))}
          </nav>
          <div className="explorer-content">
            {tab === "files"
              ? files.data?.map((f) => (
                  <div key={f.id}>
                    <button
                      className={
                        "file-row " + (s.file === f.id ? "active-row" : "")
                      }
                      onClick={() => {
                        s.setFile(s.file === f.id ? null : f.id);
                        s.setSelected(f.id);
                        s.setFocus(null);
                        setEdge(null);
                      }}
                    >
                      <ChevronRight
                        size={12}
                        style={{
                          transform: s.file === f.id ? "rotate(90deg)" : "",
                        }}
                      />
                      <FileCode2 size={14} />
                      <span title={f.path}>{f.path}</span>
                      {f.errors.length > 0 && (
                        <i
                          className="error-dot"
                          title={JSON.stringify(f.errors)}
                        />
                      )}
                    </button>
                    {s.file === f.id &&
                      symbols.data
                        ?.filter(
                          (x) =>
                            x.file_id === f.id &&
                            ["function", "class", "method"].includes(x.kind),
                        )
                        .map((x) => (
                          <button
                            className="symbol-row"
                            key={x.id}
                            onClick={() => {
                              s.setSelected(x.id);
                              s.setView("calls");
                              setEdge(null);
                            }}
                          >
                            <Braces size={12} />
                            {x.qualified_name}
                          </button>
                        ))}
                  </div>
                ))
              : symbols.data
                  ?.filter((x) =>
                    tab === "entries"
                      ? x.kind === "hook"
                      : ["function", "method", "class", "variable"].includes(
                          x.kind,
                        ),
                  )
                  .map((x) => (
                    <button
                      className={
                        "symbol-row " +
                        (s.selected === x.id ? "active-row" : "")
                      }
                      key={x.id}
                      onClick={() => {
                        s.setSelected(x.id);
                        s.setView("calls");
                        s.setFile(x.file_id);
                        setEdge(null);
                      }}
                    >
                      {x.kind === "hook" ? (
                        <Zap size={13} />
                      ) : (
                        <Braces size={13} />
                      )}
                      <span>
                        {x.qualified_name}
                        <small>
                          line {x.line} · {x.kind}
                        </small>
                      </span>
                    </button>
                  ))}
            {!s.project && (
              <p className="muted empty-small">
                Open a local folder to explore its files, symbols, and entry
                points.
              </p>
            )}
          </div>
          <div className="sidebar-foot">
            <Activity size={13} /> Local analysis · source read only
          </div>
        </aside>
        <section className="workspace">
          <div className="view-toolbar">
            <div className="view-tabs">
              {(["dependency", "calls", "flow"] as const).map((v) => (
                <button
                  key={v}
                  className={s.view === v ? "active" : ""}
                  onClick={() => s.setView(v)}
                >
                  {v === "dependency"
                    ? "Dependencies"
                    : v === "calls"
                      ? "Call graph"
                      : "Function flow"}
                </button>
              ))}
            </div>
            <label>
              Depth{" "}
              <select
                aria-label="Traversal depth"
                value={s.depth}
                onChange={(e) => s.setDepth(Number(e.target.value))}
              >
                {[0, 1, 2, 3, 4, 5, 8, 10].map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
            </label>
            <button
              onClick={() => {
                s.setFocus(null);
                s.setFile(null);
              }}
            >
              Reset focus
            </button>
          </div>
          <div className="graph-caption">
            <span>
              <span className="live-dot" />{" "}
              {s.view === "dependency"
                ? "Module relationships"
                : s.view === "calls"
                  ? "Possible call paths"
                  : "Function statements & dependencies"}
            </span>
            <span>STATIC ANALYSIS · {s.direction.toUpperCase()}</span>
          </div>
          {graph.data?.warning && (
            <div className="warning">{graph.data.warning}</div>
          )}
          {!s.project ? (
            <div className="welcome">
              <GitBranch size={40} />
              <h1>Understand the connections.</h1>
              <p>
                Explore how your code fits together.
                <br />
                Files, symbols, and possible execution paths — locally.
              </p>
              <button className="primary" onClick={open}>
                <FolderOpen size={16} />
                Open repository
              </button>
              <small>Python · JavaScript · TypeScript · TSX</small>
            </div>
          ) : running ? (
            <div className="welcome">
              <RefreshCw size={30} className="spin" />
              <h2>Analyzing repository</h2>
              <p>
                {status.data?.parsed || 0} parsed · {status.data?.skipped || 0}{" "}
                skipped · {status.data?.discovered || 0} discovered
              </p>
              <small>
                The previous scan stays intact until this scan completes.
              </small>
            </div>
          ) : graph.isLoading ? (
            <div className="welcome">Loading graph…</div>
          ) : (
            <GraphCanvas
              graph={graph.data || emptyGraph}
              selected={s.selected}
              onSelect={select}
              onEdge={setEdge}
            />
          )}
        </section>
        <aside className="inspector">
          <div className="panel-title">
            INSPECTOR{" "}
            {s.selected && (
              <button
                aria-label="Clear selection"
                onClick={() => {
                  s.setSelected(null);
                  setEdge(null);
                }}
              >
                <X size={13} />
              </button>
            )}
          </div>
          {edge ? (
            <div className="inspection">
              <span className="type-tag">{edge.type}</span>
              <h2>Relationship</h2>
              <dl>
                <dt>Source</dt>
                <dd>
                  {graph.data?.nodes.find((n) => n.id === edge.source)?.label}
                </dd>
                <dt>Target</dt>
                <dd>
                  {graph.data?.nodes.find((n) => n.id === edge.target)?.label}
                </dd>
                <dt>Resolution</dt>
                <dd>{edge.resolution}</dd>
                <dt>Location</dt>
                <dd>
                  {String(edge.metadata.file)}:{String(edge.metadata.line)}
                </dd>
              </dl>
              <pre>{JSON.stringify(edge.metadata, null, 2)}</pre>
              <button onClick={() => select(edge.target)}>
                Inspect target
              </button>
            </div>
          ) : detail.data && selectedSymbol ? (
            <div className="inspection">
              <span className="type-tag">{detail.data.kind}</span>
              <h2>{detail.data.name}</h2>
              <p className="mono muted">{detail.data.qualified_name}</p>
              <dl>
                <dt>Source</dt>
                <dd>
                  {detail.data.file}:{detail.data.line}
                </dd>
                <dt>Resolution</dt>
                <dd>{detail.data.resolution}</dd>
                <dt>Scope</dt>
                <dd>
                  {symbols.data?.find((x) => x.id === detail.data?.scope_id)
                    ?.qualified_name || "module"}
                </dd>
                {Array.isArray(detail.data.metadata.parameters) && (
                  <>
                    <dt>Parameters</dt>
                    <dd>
                      {(detail.data.metadata.parameters as string[]).join(
                        ", ",
                      ) || "none"}
                    </dd>
                  </>
                )}
                {!!detail.data.metadata.return_annotation && (
                  <>
                    <dt>Returns</dt>
                    <dd>{String(detail.data.metadata.return_annotation)}</dd>
                  </>
                )}
              </dl>
              {["function", "method"].includes(detail.data.kind) && (
                <div className="explore-actions">
                  <button
                    onClick={() => explore(detail.data!.id, "downstream")}
                  >
                    <ArrowDownRight size={14} />
                    Downstream
                  </button>
                  <button onClick={() => explore(detail.data!.id, "upstream")}>
                    <ArrowUpRight size={14} />
                    Upstream
                  </button>
                  <button
                    onClick={() => {
                      s.setView("flow");
                      s.setFocus(detail.data!.id);
                    }}
                  >
                    View function flow
                  </button>
                </div>
              )}
              <h4>
                CALLEES <span>{detail.data.callees.length}</span>
              </h4>
              {detail.data.callees.map((c) => (
                <button
                  className="relation-row"
                  key={c.id}
                  onClick={() =>
                    c.target_id && explore(c.target_id, "downstream")
                  }
                >
                  <span>
                    {c.name}
                    <small>
                      {c.resolution}
                      {c.metadata.conditional ? " · conditional" : ""}
                    </small>
                  </span>
                  <ChevronRight size={12} />
                </button>
              ))}
              <h4>
                CALLERS <span>{detail.data.callers.length}</span>
              </h4>
              {detail.data.callers.map((c) => (
                <button
                  className="relation-row"
                  key={c.id}
                  onClick={() =>
                    (c.caller_id || c.scope_id) &&
                    explore((c.caller_id || c.scope_id)!, "upstream")
                  }
                >
                  <span>
                    {c.caller_name || "module"}
                    <small>line {c.line}</small>
                  </span>
                  <ChevronRight size={12} />
                </button>
              ))}
              <h4>
                REFERENCES <span>{detail.data.references.length}</span>
              </h4>
              {detail.data.references.slice(0, 20).map((r) => (
                <div className="reference" key={r.id}>
                  {files.data?.find((f) => f.id === r.file_id)?.path}:{r.line}
                </div>
              ))}
              <h4>SOURCE PREVIEW</h4>
              {detail.data.warning && (
                <p className="warning">{detail.data.warning}</p>
              )}
              <div className="source-preview">
                {detail.data.snippet.split("\n").map((line, i) => (
                  <div key={i}>
                    <span>{detail.data!.snippet_line + i}</span>
                    <code>
                      <SourceLine line={line} />
                    </code>
                  </div>
                ))}
              </div>
            </div>
          ) : activeFile ? (
            <div className="inspection">
              <span className="type-tag">file</span>
              <h2>{activeFile.path}</h2>
              <dl>
                <dt>Language</dt>
                <dd>{activeFile.language}</dd>
                <dt>Parse status</dt>
                <dd>{activeFile.status}</dd>
              </dl>
              {activeFile.errors.map((e, i) => (
                <p className="warning" key={i}>
                  {e.message || `${e.type} at line ${e.line}`}
                </p>
              ))}
              <button onClick={() => s.setView("calls")}>
                Explore file calls
              </button>
            </div>
          ) : node ? (
            <div className="inspection">
              <span className="type-tag">{node.type}</span>
              <h2>{node.label}</h2>
              <p className="muted">{node.file}</p>
              <pre>{JSON.stringify(node.metadata, null, 2)}</pre>
            </div>
          ) : (
            <div className="inspector-empty">
              <Braces size={26} />
              <p>
                Select a node or relationship
                <br />
                to inspect its details.
              </p>
            </div>
          )}
        </aside>
      </main>
      <footer>
        <span>
          <span className={"live-dot " + (running ? "busy" : "")} />
          {status.data?.status === "complete"
            ? "Analysis complete"
            : running
              ? "Analyzing"
              : "Ready"}
        </span>
        <span>Files {files.data?.length || status.data?.discovered || 0}</span>
        <span>Symbols {status.data?.symbols ?? symbols.data?.length ?? 0}</span>
        <span>Errors {status.data?.errors || 0}</span>
        <span className="footer-right">
          Possible paths, not a runtime trace
        </span>
      </footer>
    </div>
  );
}
