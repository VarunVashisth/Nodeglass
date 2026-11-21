export interface Project {
  id: string;
  name: string;
  path: string;
}
export interface SourceFile {
  id: string;
  path: string;
  language: string;
  status: string;
  errors: { message?: string; line?: number; type?: string }[];
}
export interface SymbolInfo {
  id: string;
  name: string;
  qualified_name: string;
  kind: string;
  file_id: string;
  line: number;
  scope_id: string | null;
  resolution: string;
  metadata: Record<string, unknown>;
  target_id?: string;
  caller_id?: string;
  caller_name?: string;
}
export interface SymbolDetail extends SymbolInfo {
  file: string;
  snippet: string;
  snippet_line: number;
  warning?: string;
  callers: SymbolInfo[];
  callees: SymbolInfo[];
  references: SymbolInfo[];
}
export interface GraphNode {
  id: string;
  type: string;
  label: string;
  file: string;
  metadata: Record<string, unknown>;
}
export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  resolution: string;
  metadata: Record<string, unknown>;
}
export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated: boolean;
  warning?: string;
}
export interface Status {
  status: string;
  discovered?: number;
  parsed?: number;
  skipped?: number;
  errors?: number;
  unchanged?: number;
  deleted?: number;
  symbols?: number;
  message?: string;
}
declare global {
  interface Window {
    nodeglass?: {
      connection(): Promise<{ url: string; token: string }>;
      chooseRepository(): Promise<Project | null>;
    };
  }
}
