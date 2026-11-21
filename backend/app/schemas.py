from typing import Any

from pydantic import BaseModel, Field


class OpenProject(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


class Project(BaseModel):
    id: str
    name: str
    path: str


class GraphNode(BaseModel):
    id: str
    type: str
    label: str
    file: str
    metadata: dict[str, Any]


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str
    resolution: str
    metadata: dict[str, Any]


class Graph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool = False
    warning: str | None = None
