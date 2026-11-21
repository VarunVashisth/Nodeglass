import { create } from "zustand";
import type { Project } from "./types";
type View = "dependency" | "calls" | "flow";
interface State {
  project: Project | null;
  view: View;
  focus: string | null;
  selected: string | null;
  file: string | null;
  direction: "downstream" | "upstream";
  depth: number;
  setProject: (project: Project) => void;
  setView: (view: View) => void;
  setFocus: (focus: string | null) => void;
  setSelected: (selected: string | null) => void;
  setFile: (file: string | null) => void;
  setDirection: (direction: "downstream" | "upstream") => void;
  setDepth: (depth: number) => void;
}
export const useStore = create<State>((set) => ({
  project: null,
  view: "dependency",
  focus: null,
  selected: null,
  file: null,
  direction: "downstream",
  depth: 2,
  setProject: (project) =>
    set({
      project,
      selected: null,
      focus: null,
      file: null,
      view: "dependency",
    }),
  setView: (view) => set({ view, focus: null }),
  setFocus: (focus) => set({ focus }),
  setSelected: (selected) => set({ selected }),
  setFile: (file) => set({ file, focus: null }),
  setDirection: (direction) => set({ direction }),
  setDepth: (depth) => set({ depth }),
}));
