from __future__ import annotations

"""
Dependency graph analyser.

Detects:
  circular_dependencies  -- nx.simple_cycles
  orphan_classes         -- isolated nodes (no in or out edges)
  highly_coupled         -- classes whose total degree exceeds a threshold
  layer_violations       -- lower-layer class depending on higher-layer class
                            (e.g. repository -> service, service -> controller)

Metrics:
  afferent coupling  Ca  -- how many classes depend on this class (in-degree)
  efferent coupling  Ce  -- how many classes this class depends on (out-degree)
  instability        I   -- Ce / (Ca + Ce),  0 = stable,  1 = instable
"""

from dataclasses import dataclass
from typing import List, Tuple

import networkx as nx


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CircularDependency:
    cycle: List[str]

    def __str__(self) -> str:
        return " -> ".join(self.cycle + [self.cycle[0]])

    def to_dict(self) -> dict:
        return {"cycle": self.cycle, "length": len(self.cycle)}


@dataclass
class CouplingMetrics:
    class_name: str
    afferent_coupling: int   # Ca
    efferent_coupling: int   # Ce
    instability: float       # I = Ce / (Ca + Ce)

    @property
    def total_coupling(self) -> int:
        return self.afferent_coupling + self.efferent_coupling

    @property
    def is_highly_coupled(self) -> bool:
        return self.total_coupling > 4

    def to_dict(self) -> dict:
        return {
            "class_name": self.class_name,
            "Ca": self.afferent_coupling,
            "Ce": self.efferent_coupling,
            "instability": round(self.instability, 3),
            "highly_coupled": self.is_highly_coupled,
        }


@dataclass
class AnalysisReport:
    circular_dependencies: List[CircularDependency]
    orphan_classes: List[str]
    highly_coupled: List[CouplingMetrics]
    layer_violations: List[Tuple[str, str]]
    coupling_metrics: List[CouplingMetrics]

    def summary(self) -> str:
        sep = "-" * 60
        lines = [
            sep,
            "  Dependency Analysis Report",
            sep,
            f"  Classes analysed     : {len(self.coupling_metrics)}",
            f"  Circular deps        : {len(self.circular_dependencies)}",
            f"  Orphan classes       : {len(self.orphan_classes)}",
            f"  Highly coupled       : {len(self.highly_coupled)}",
            f"  Layer violations     : {len(self.layer_violations)}",
        ]

        if self.circular_dependencies:
            lines += ["", "  Circular Dependencies:"]
            for c in self.circular_dependencies:
                lines.append(f"    {c}")

        if self.orphan_classes:
            lines += ["", "  Orphan Classes (no connections):"]
            for o in self.orphan_classes:
                lines.append(f"    {o}")

        if self.highly_coupled:
            lines += ["", "  Highly Coupled (total degree > 4):"]
            for m in sorted(self.highly_coupled, key=lambda x: -x.total_coupling):
                lines.append(
                    f"    {m.class_name:<35} "
                    f"Ca={m.afferent_coupling}  Ce={m.efferent_coupling}  "
                    f"I={m.instability:.2f}"
                )

        if self.layer_violations:
            lines += ["", "  Layer Violations (lower layer -> higher layer):"]
            for src, tgt in self.layer_violations:
                lines.append(f"    {src} -> {tgt}")

        lines.append(sep)
        return chr(10).join(lines)

    def to_dict(self) -> dict:
        return {
            "circular_dependencies": [c.to_dict() for c in self.circular_dependencies],
            "orphan_classes": self.orphan_classes,
            "highly_coupled": [m.to_dict() for m in self.highly_coupled],
            "layer_violations": [
                {"source": s, "target": t} for s, t in self.layer_violations
            ],
            "coupling_metrics": [m.to_dict() for m in self.coupling_metrics],
        }


# ---------------------------------------------------------------------------
# Layer ordering -- higher number = higher architectural layer
# ---------------------------------------------------------------------------
_LAYER_RANK = {
    "controller": 3,
    "service":    2,
    "component":  2,
    "repository": 1,
    "bean":       1,
}


# ---------------------------------------------------------------------------
# Individual detectors
# ---------------------------------------------------------------------------

def detect_circular_dependencies(G: nx.DiGraph) -> List[CircularDependency]:
    """All simple cycles in the dependency graph, shortest first."""
    return sorted(
        [CircularDependency(cycle=c) for c in nx.simple_cycles(G)],
        key=lambda c: len(c.cycle),
    )


def detect_orphan_classes(G: nx.DiGraph) -> List[str]:
    """Classes that have zero in-edges AND zero out-edges."""
    return sorted(
        n for n in G.nodes if G.in_degree(n) == 0 and G.out_degree(n) == 0
    )


def compute_coupling_metrics(G: nx.DiGraph) -> List[CouplingMetrics]:
    """Afferent/efferent coupling and instability for every class."""
    metrics = []
    for node in G.nodes:
        ca = G.in_degree(node)
        ce = G.out_degree(node)
        total = ca + ce
        metrics.append(CouplingMetrics(
            class_name=node,
            afferent_coupling=ca,
            efferent_coupling=ce,
            instability=ce / total if total > 0 else 0.0,
        ))
    return sorted(metrics, key=lambda m: -m.total_coupling)


def detect_layer_violations(G: nx.DiGraph) -> List[Tuple[str, str]]:
    """
    A layer violation occurs when a lower-layer class depends on a
    higher-layer class, e.g. repository -> service.
    """
    violations = []
    for src, tgt in G.edges:
        src_rank = _LAYER_RANK.get(G.nodes[src].get("class_type", ""), 0)
        tgt_rank = _LAYER_RANK.get(G.nodes[tgt].get("class_type", ""), 0)
        if src_rank > 0 and tgt_rank > 0 and src_rank < tgt_rank:
            violations.append((src, tgt))
    return violations


def analyze(G: nx.DiGraph) -> AnalysisReport:
    """Run all analyses and return a consolidated AnalysisReport."""
    metrics = compute_coupling_metrics(G)
    return AnalysisReport(
        circular_dependencies=detect_circular_dependencies(G),
        orphan_classes=detect_orphan_classes(G),
        highly_coupled=[m for m in metrics if m.is_highly_coupled],
        layer_violations=detect_layer_violations(G),
        coupling_metrics=metrics,
    )
