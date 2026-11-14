"""
Selection engines: LFNS (Proposed), Nearest-Node (Baseline), and Round-Robin (Baseline).
"""

import time
from typing import Dict, List, Optional
from .models import FogNode, HealthTask, NodeEstimate, SelectionResult


class LFNSEngine:
    """
    Latency-Aware Fog Node Selection (LFNS) Engine.
    Filters eligible nodes, calculates Estimatenode = Tnetwork + Tqueue + Tprocessing,
    resolves ties with communication cost, and updates state immediately.
    """

    def __init__(self, overhead_ms: float = 5.0):
        self.overhead_ms = overhead_ms

    def select_node(self, task: HealthTask, nodes: Dict[str, FogNode]) -> SelectionResult:
        start_time = time.perf_counter()

        estimates: Dict[str, NodeEstimate] = {}
        eligible_nodes: List[FogNode] = []

        # 1. Filter nodes
        for node in nodes.values():
            if node.is_eligible(task):
                eligible_nodes.append(node)
                t_net = node.base_network_rtt_ms
                t_queue = node.current_queue_wait_ms
                t_proc = node.calculate_processing_time(task)
                t_est = t_net + t_queue + t_proc

                estimates[node.node_id] = NodeEstimate(
                    node_id=node.node_id,
                    t_network=t_net,
                    t_queue=t_queue,
                    t_processing=t_proc,
                    t_total_estimated=t_est,
                    communication_cost=node.communication_cost_score,
                )

        if not eligible_nodes:
            selection_time = (time.perf_counter() - start_time) * 1000.0 + self.overhead_ms
            return SelectionResult(
                selected_node_id=None,
                estimates=estimates,
                selection_overhead_ms=selection_time,
                algorithm="LFNS",
                is_successful=False,
                failure_reason="No connected, authorized, or capable fog nodes available.",
            )

        # 2. Select node with smallest estimate, tiebreaker: lower communication cost
        best_node_id = min(
            estimates.keys(),
            key=lambda nid: (estimates[nid].t_total_estimated, estimates[nid].communication_cost),
        )

        # 3. Workload update: immediately reflect assigned task execution in selected node queue
        assigned_node = nodes[best_node_id]
        assigned_proc_time = assigned_node.calculate_processing_time(task)
        assigned_node.current_queue_wait_ms += assigned_proc_time

        selection_time = (time.perf_counter() - start_time) * 1000.0 + self.overhead_ms

        return SelectionResult(
            selected_node_id=best_node_id,
            estimates=estimates,
            selection_overhead_ms=selection_time,
            algorithm="LFNS",
            is_successful=True,
        )


class NearestNodeEngine:
    """
    Baseline 1: Nearest-Node Selection.
    Selects the eligible node with the lowest network latency.
    """

    def __init__(self, overhead_ms: float = 5.0):
        self.overhead_ms = overhead_ms

    def select_node(self, task: HealthTask, nodes: Dict[str, FogNode]) -> SelectionResult:
        start_time = time.perf_counter()

        eligible_nodes = [node for node in nodes.values() if node.is_eligible(task)]

        if not eligible_nodes:
            selection_time = (time.perf_counter() - start_time) * 1000.0 + self.overhead_ms
            return SelectionResult(
                selected_node_id=None,
                estimates={},
                selection_overhead_ms=selection_time,
                algorithm="NEAREST_NODE",
                is_successful=False,
                failure_reason="No eligible fog nodes found.",
            )

        # Pick node with minimum network RTT
        best_node = min(eligible_nodes, key=lambda n: n.base_network_rtt_ms)

        # Update queue
        assigned_proc_time = best_node.calculate_processing_time(task)
        best_node.current_queue_wait_ms += assigned_proc_time

        selection_time = (time.perf_counter() - start_time) * 1000.0 + self.overhead_ms

        return SelectionResult(
            selected_node_id=best_node.node_id,
            estimates={},
            selection_overhead_ms=selection_time,
            algorithm="NEAREST_NODE",
            is_successful=True,
        )


class RoundRobinEngine:
    """
    Baseline 2: Round-Robin Selection.
    Distributes requests sequentially among eligible nodes.
    """

    def __init__(self, overhead_ms: float = 5.0):
        self.overhead_ms = overhead_ms
        self.last_index = 0

    def select_node(self, task: HealthTask, nodes: Dict[str, FogNode]) -> SelectionResult:
        start_time = time.perf_counter()

        sorted_node_keys = sorted(nodes.keys())
        eligible_nodes = [nodes[k] for k in sorted_node_keys if nodes[k].is_eligible(task)]

        if not eligible_nodes:
            selection_time = (time.perf_counter() - start_time) * 1000.0 + self.overhead_ms
            return SelectionResult(
                selected_node_id=None,
                estimates={},
                selection_overhead_ms=selection_time,
                algorithm="ROUND_ROBIN",
                is_successful=False,
                failure_reason="No eligible fog nodes found.",
            )

        selected_node = eligible_nodes[self.last_index % len(eligible_nodes)]
        self.last_index = (self.last_index + 1) % len(eligible_nodes)

        # Update queue
        assigned_proc_time = selected_node.calculate_processing_time(task)
        selected_node.current_queue_wait_ms += assigned_proc_time

        selection_time = (time.perf_counter() - start_time) * 1000.0 + self.overhead_ms

        return SelectionResult(
            selected_node_id=selected_node.node_id,
            estimates={},
            selection_overhead_ms=selection_time,
            algorithm="ROUND_ROBIN",
            is_successful=True,
        )
