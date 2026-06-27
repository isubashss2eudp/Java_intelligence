from __future__ import annotations

"""
Graph query API -- structured, named queries over the dependency graph.

All methods return plain dicts/lists so results can be serialised to JSON
or passed directly to an LLM for natural-language answers.

Example usage:
    engine = DependencyQueryEngine(graph)
    engine.who_depends_on("CustomerRepository")
    engine.dependency_chain("OrderController", "CustomerRepository")
    engine.most_depended_on(top_n=5)
"""

from typing import Any, Dict, List, Optional

import networkx as nx


class DependencyQueryEngine:
    """High-level named-query interface for a Java dependency graph."""

    def __init__(self, G: nx.DiGraph) -> None:
        self._G = G

    # ------------------------------------------------------------------
    # Core queries
    # ------------------------------------------------------------------

    def who_depends_on(self, class_name: str) -> List[Dict[str, Any]]:
        """
        All classes (direct and transitive) that depend on class_name.
        Answers: "Which services depend on CustomerRepository?"
        """
        if class_name not in self._G:
            return []
        results = []
        for cls in nx.ancestors(self._G, class_name):
            is_direct = self._G.has_edge(cls, class_name)
            edge = self._G.get_edge_data(cls, class_name) or {}
            results.append({
                "class":        cls,
                "package":      self._G.nodes[cls].get("package", ""),
                "class_type":   self._G.nodes[cls].get("class_type", ""),
                "relationship": "direct" if is_direct else "transitive",
                "dep_type":     edge.get("dep_type", "") if is_direct else "transitive",
            })
        return sorted(results, key=lambda r: (r["relationship"], r["class"]))

    def direct_dependents(self, class_name: str) -> List[Dict[str, Any]]:
        """Immediate predecessors of class_name (direct in-neighbours)."""
        if class_name not in self._G:
            return []
        results = []
        for cls in self._G.predecessors(class_name):
            edge = self._G.get_edge_data(cls, class_name) or {}
            results.append({
                "class":      cls,
                "package":    self._G.nodes[cls].get("package", ""),
                "class_type": self._G.nodes[cls].get("class_type", ""),
                "dep_type":   edge.get("dep_type", ""),
                "line":       edge.get("line", 0),
            })
        return sorted(results, key=lambda r: r["class"])

    def get_dependencies(self, class_name: str) -> List[Dict[str, Any]]:
        """
        All classes (direct and transitive) that class_name depends on.
        Answers: "What does OrderService depend on?"
        """
        if class_name not in self._G:
            return []
        results = []
        for cls in nx.descendants(self._G, class_name):
            is_direct = self._G.has_edge(class_name, cls)
            edge = self._G.get_edge_data(class_name, cls) or {}
            results.append({
                "class":        cls,
                "package":      self._G.nodes[cls].get("package", ""),
                "class_type":   self._G.nodes[cls].get("class_type", ""),
                "relationship": "direct" if is_direct else "transitive",
                "dep_type":     edge.get("dep_type", "") if is_direct else "transitive",
            })
        return sorted(results, key=lambda r: (r["relationship"], r["class"]))

    def dependency_chain(
        self, source: str, target: str
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Shortest dependency path from source to target.
        Answers: "What is the dependency chain between Controller and DAO?"
        Returns None when no path exists.
        """
        if source not in self._G or target not in self._G:
            return None
        try:
            path = nx.shortest_path(self._G, source=source, target=target)
        except nx.NetworkXNoPath:
            return None

        chain = []
        for i, node in enumerate(path):
            entry: Dict[str, Any] = {
                "step":       i,
                "class":      node,
                "package":    self._G.nodes[node].get("package", ""),
                "class_type": self._G.nodes[node].get("class_type", ""),
            }
            if i < len(path) - 1:
                edge = self._G.get_edge_data(node, path[i + 1]) or {}
                entry["dep_type"]  = edge.get("dep_type", "")
                entry["next"]      = path[i + 1]
            chain.append(entry)
        return chain

    def all_paths(
        self, source: str, target: str, cutoff: int = 10
    ) -> List[List[str]]:
        """All simple paths between source and target (up to cutoff length)."""
        if source not in self._G or target not in self._G:
            return []
        return list(nx.all_simple_paths(self._G, source, target, cutoff=cutoff))

    # ------------------------------------------------------------------
    # Structural queries
    # ------------------------------------------------------------------

    def classes_by_type(self, class_type: str) -> List[str]:
        """All classes of a given architectural type."""
        return sorted(
            n for n, d in self._G.nodes(data=True)
            if d.get("class_type") == class_type
        )

    def classes_in_package(self, package_prefix: str) -> List[str]:
        """All classes whose package starts with package_prefix."""
        return sorted(
            n for n, d in self._G.nodes(data=True)
            if d.get("package", "").startswith(package_prefix)
        )

    def most_depended_on(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """Top N classes with the highest number of dependents (in-degree)."""
        nodes = sorted(self._G.nodes, key=lambda n: -self._G.in_degree(n))[:top_n]
        return [
            {
                "class":      n,
                "package":    self._G.nodes[n].get("package", ""),
                "class_type": self._G.nodes[n].get("class_type", ""),
                "dependents": self._G.in_degree(n),
            }
            for n in nodes
        ]

    def most_dependencies(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """Top N classes that depend on the most other classes (out-degree)."""
        nodes = sorted(self._G.nodes, key=lambda n: -self._G.out_degree(n))[:top_n]
        return [
            {
                "class":        n,
                "package":      self._G.nodes[n].get("package", ""),
                "class_type":   self._G.nodes[n].get("class_type", ""),
                "dependencies": self._G.out_degree(n),
            }
            for n in nodes
        ]

    def subgraph_for(self, class_name: str, depth: int = 2) -> nx.DiGraph:
        """
        Local neighborhood around class_name up to the given depth.
        Useful for scoped visualisation or LLM context narrowing.
        """
        if class_name not in self._G:
            return nx.DiGraph()
        return nx.ego_graph(self._G, class_name, radius=depth, undirected=True)

    def graph_stats(self) -> Dict[str, Any]:
        """High-level statistics about the graph."""
        return {
            "total_classes":       self._G.number_of_nodes(),
            "total_dependencies":  self._G.number_of_edges(),
            "is_dag":              nx.is_directed_acyclic_graph(self._G),
            "weakly_connected_components": nx.number_weakly_connected_components(self._G),
            "density":             round(nx.density(self._G), 4),
        }

    def format_chain(self, chain: Optional[List[Dict[str, Any]]]) -> str:
        """Pretty-print a dependency chain as a readable string."""
        if not chain:
            return "No path found."
        parts = []
        for entry in chain:
            label = f"{entry['class']} ({entry['class_type']})"
            if "next" in entry:
                label += f" --[{entry['dep_type']}]-->"
            parts.append(label)
        return " ".join(parts)
