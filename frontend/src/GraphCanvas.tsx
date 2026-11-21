import { useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  MarkerType,
  useEdgesState,
  useNodesState,
  useReactFlow,
  ReactFlowProvider,
  type NodeProps,
  type Node,
  type Edge,
} from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import { FileCode2, Braces, Box, Zap, CircleHelp } from "lucide-react";
import type { Graph, GraphEdge, GraphNode } from "./types";
import "@xyflow/react/dist/style.css";

type Data = { entity: GraphNode; vertical: boolean };
function CodeNode({ data, selected }: NodeProps<Node<Data>>) {
  const n = data.entity;
  const Icon =
    n.type === "file" || n.type === "module"
      ? FileCode2
      : n.type === "class"
        ? Box
        : n.type === "entry_point"
          ? Zap
          : n.type === "unresolved"
            ? CircleHelp
            : Braces;
  return (
    <div className={`code-node ${n.type} ${selected ? "selected" : ""}`}>
      <Handle
        type="target"
        position={data.vertical ? Position.Top : Position.Left}
      />
      <div className="node-kind">
        <Icon size={13} />
        {n.type.replace("_", " ")}
      </div>
      <strong title={n.label}>{n.label}</strong>
      <small>
        {n.type === "file"
          ? String(n.metadata.language)
          : n.file + (n.metadata.line ? ":" + n.metadata.line : "")}
      </small>
      <Handle
        type="source"
        position={data.vertical ? Position.Bottom : Position.Right}
      />
    </div>
  );
}
const nodeTypes = { code: CodeNode };
function Canvas({
  graph,
  selected,
  onSelect,
  onEdge,
}: {
  graph: Graph;
  selected: string | null;
  onSelect: (id: string) => void;
  onEdge: (edge: GraphEdge) => void;
}) {
  const [vertical, setVertical] = useState(false);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const flow = useReactFlow();
  useEffect(
    () => setHidden((previous) => (previous.size ? new Set() : previous)),
    [graph],
  );
  const layout = useMemo(() => {
    const visible = graph.nodes.filter((n) => !hidden.has(n.id));
    const ids = new Set(visible.map((n) => n.id));
    const connected = new Set<string>([selected || ""]);
    graph.edges.forEach((e) => {
      if (e.source === selected || e.target === selected) {
        connected.add(e.source);
        connected.add(e.target);
      }
    });
    const g = new dagre.graphlib.Graph({ multigraph: true })
      .setGraph({ rankdir: vertical ? "TB" : "LR", nodesep: 38, ranksep: 95 })
      .setDefaultEdgeLabel(() => ({}));
    visible.forEach((n) => g.setNode(n.id, { width: 210, height: 90 }));
    graph.edges
      .filter((e) => ids.has(e.source) && ids.has(e.target))
      .forEach((e) => g.setEdge(e.source, e.target, {}, e.id));
    dagre.layout(g);
    const nodes: Node<Data>[] = visible.map((n) => ({
      id: n.id,
      type: "code",
      data: { entity: n, vertical },
      position: { x: g.node(n.id).x - 105, y: g.node(n.id).y - 45 },
      selected: n.id === selected,
      style: { opacity: selected && !connected.has(n.id) ? 0.3 : 1 },
    }));
    const edges: Edge[] = graph.edges
      .filter((e) => ids.has(e.source) && ids.has(e.target))
      .map((e) => ({
        ...e,
        type: "smoothstep",
        label:
          e.type === "CALLS" && e.metadata.conditional
            ? "calls · conditional"
            : e.type.toLowerCase().replaceAll("_", " "),
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: e.resolution === "resolved" ? "#6f9dba" : "#727780",
        },
        style: {
          stroke: e.resolution === "resolved" ? "#6f9dba" : "#727780",
          strokeDasharray:
            e.type === "IMPORTS"
              ? "6 4"
              : e.resolution !== "resolved"
                ? "3 4"
                : undefined,
          opacity:
            selected && e.source !== selected && e.target !== selected
              ? 0.2
              : 1,
        },
        labelStyle: { fill: "#aeb8c7", fontSize: 10 },
        labelBgStyle: { fill: "#15191f" },
        labelBgPadding: [5, 3] as [number, number],
      }));
    return { nodes, edges };
  }, [graph, selected, vertical, hidden]);
  const [nodes, setNodes, onNodesChange] = useNodesState(layout.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(layout.edges);
  useEffect(() => {
    setNodes((previous) =>
      layout.nodes.map((node) => ({
        ...node,
        measured: previous.find((item) => item.id === node.id)?.measured,
      })),
    );
    setEdges(layout.edges);
    const t = setTimeout(
      () => flow.fitView({ padding: 0.22, duration: 150 }),
      40,
    );
    return () => clearTimeout(t);
  }, [layout, setNodes, setEdges, flow]);
  function collapse() {
    if (!selected) return;
    setHidden(
      new Set(
        graph.edges
          .filter((e) => e.source === selected && e.target !== selected)
          .map((e) => e.target),
      ),
    );
  }
  return (
    <div className="graph-area">
      <div className="canvas-tools">
        <button onClick={() => setVertical(!vertical)}>
          {vertical ? "Top → bottom" : "Left → right"}
        </button>
        <button onClick={() => flow.fitView({ padding: 0.2 })}>
          Fit graph
        </button>
        <button disabled={!selected} onClick={collapse}>
          Collapse children
        </button>
        {hidden.size > 0 && (
          <button onClick={() => setHidden(new Set())}>Expand all</button>
        )}
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={(_, node) => onSelect(node.id)}
        onEdgeClick={(_, edge) => {
          const e = graph.edges.find((e) => e.id === edge.id);
          if (e) onEdge(e);
        }}
        fitView
        minZoom={0.1}
        maxZoom={2}
        colorMode="dark"
      >
        <Background gap={22} size={1} color="#293039" />
        <Controls showInteractive={false} />
      </ReactFlow>
      {!graph.nodes.length && (
        <div className="canvas-empty">
          <Braces size={30} />
          <h3>No relationships in this view</h3>
          <p>
            {graph.warning ||
              "Scan a repository, select a file, or focus a function."}
          </p>
        </div>
      )}
      <div className="legend">
        <span>── calls</span>
        <span>╌╌ imports</span>
        <span>··· inferred / unresolved</span>
        <span>
          {graph.nodes.length} nodes · {graph.edges.length} edges
        </span>
      </div>
    </div>
  );
}
export default function GraphCanvas(props: Parameters<typeof Canvas>[0]) {
  return (
    <ReactFlowProvider>
      <Canvas {...props} />
    </ReactFlowProvider>
  );
}
