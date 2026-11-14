"""
Simulation framework for LFNS evaluation.
Tests scenarios:
  1. Light, medium, and heavy load
  2. One busy node
  3. Slower network or larger payload
  4. Node disconnection
Compares LFNS against Nearest-Node and Round-Robin baselines.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import copy
import random
from typing import Dict, List, Tuple
from core.models import (
    FogNode,
    HealthTask,
    TaskType,
    NodeStatus,
    SimulationScenarioResult,
)
from core.lfns_engine import LFNSEngine, NearestNodeEngine, RoundRobinEngine


def create_standard_network() -> Dict[str, FogNode]:
    """Creates the standard 4-node fog network environment."""
    return {
        "F1": FogNode(
            node_id="F1",
            name="Ward gateway",
            status=NodeStatus.CONNECTED,
            is_authorized=True,
            supported_tasks=[TaskType.ECG_ANALYSIS, TaskType.PULSE_SPO2_PROCESS, TaskType.VITALS_FUSION],
            base_network_rtt_ms=10.0,
            compute_capacity_units_per_ms=1.5,
            total_memory_mb=2048,
            available_memory_mb=1024,
            communication_cost_score=1.0,
            current_queue_wait_ms=0.0,
        ),
        "F2": FogNode(
            node_id="F2",
            name="Caregiver tablet",
            status=NodeStatus.CONNECTED,
            is_authorized=True,
            supported_tasks=[TaskType.ECG_ANALYSIS, TaskType.PULSE_SPO2_PROCESS, TaskType.VITALS_FUSION],
            base_network_rtt_ms=20.0,
            compute_capacity_units_per_ms=2.0,
            total_memory_mb=4096,
            available_memory_mb=2048,
            communication_cost_score=1.2,
            current_queue_wait_ms=0.0,
        ),
        "F3": FogNode(
            node_id="F3",
            name="Clinic server",
            status=NodeStatus.CONNECTED,
            is_authorized=True,
            supported_tasks=[TaskType.ECG_ANALYSIS, TaskType.PULSE_SPO2_PROCESS, TaskType.NIBP_TRENDING, TaskType.VITALS_FUSION],
            base_network_rtt_ms=30.0,
            compute_capacity_units_per_ms=4.0,
            total_memory_mb=8192,
            available_memory_mb=6144,
            communication_cost_score=1.5,
            current_queue_wait_ms=0.0,
        ),
        "F4": FogNode(
            node_id="F4",
            name="Hospital server",
            status=NodeStatus.CONNECTED,
            is_authorized=True,
            supported_tasks=[TaskType.ECG_ANALYSIS, TaskType.PULSE_SPO2_PROCESS, TaskType.NIBP_TRENDING, TaskType.VITALS_FUSION],
            base_network_rtt_ms=50.0,
            compute_capacity_units_per_ms=8.0,
            total_memory_mb=32768,
            available_memory_mb=28000,
            communication_cost_score=2.0,
            current_queue_wait_ms=0.0,
        ),
    }


def generate_workload(num_tasks: int, arrival_rate: str = "medium") -> List[Tuple[float, HealthTask]]:
    """
    Generates a stream of timestamped health tasks with inter-arrival intervals.
    """
    mean_interval = 20.0  # ms
    if arrival_rate == "light":
        mean_interval = 60.0
    elif arrival_rate == "heavy":
        mean_interval = 5.0

    tasks = []
    current_time = 0.0

    for i in range(num_tasks):
        # Exponential arrival
        inter_arrival = random.expovariate(1.0 / mean_interval)
        current_time += inter_arrival

        task_type = random.choice([
            TaskType.ECG_ANALYSIS,
            TaskType.PULSE_SPO2_PROCESS,
            TaskType.VITALS_FUSION
        ])

        compute = 30.0 if task_type == TaskType.PULSE_SPO2_PROCESS else 60.0
        payload = 512 if task_type == TaskType.PULSE_SPO2_PROCESS else 2048

        task = HealthTask(
            task_id=f"TASK-{i:04d}",
            task_type=task_type,
            payload_size_bytes=payload,
            required_memory_mb=32,
            compute_units=compute,
            created_at_ms=current_time,
        )
        tasks.append((current_time, task))

    return tasks


def run_single_simulation(
    scenario_name: str,
    algorithm: str,
    tasks_with_time: List[Tuple[float, HealthTask]],
    nodes_template: Dict[str, FogNode],
) -> SimulationScenarioResult:
    """Executes a discrete-event simulation run."""
    nodes = copy.deepcopy(nodes_template)
    overhead_ms = 5.0

    if algorithm == "LFNS":
        engine = LFNSEngine(overhead_ms=overhead_ms)
    elif algorithm == "NEAREST_NODE":
        engine = NearestNodeEngine(overhead_ms=overhead_ms)
    elif algorithm == "ROUND_ROBIN":
        engine = RoundRobinEngine(overhead_ms=overhead_ms)
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")

    response_times: List[float] = []
    node_distribution: Dict[str, int] = {nid: 0 for nid in nodes.keys()}
    failed_tasks = 0
    sim_clock = 0.0

    for arrival_time, task in tasks_with_time:
        # Time elapsed since last event: drain queues
        time_delta = max(0.0, arrival_time - sim_clock)
        sim_clock = arrival_time

        for node in nodes.values():
            node.current_queue_wait_ms = max(0.0, node.current_queue_wait_ms - time_delta)

        # Execute selection
        result = engine.select_node(task, nodes)

        if not result.is_successful or result.selected_node_id is None:
            failed_tasks += 1
            continue

        selected_id = result.selected_node_id
        node_distribution[selected_id] = node_distribution.get(selected_id, 0) + 1
        node = nodes[selected_id]

        t_net = node.base_network_rtt_ms
        t_proc = node.calculate_processing_time(task)
        # Note: current_queue_wait_ms already includes the task's own processing addition from engine
        # The wait before this task was (queue - proc)
        t_wait = max(0.0, node.current_queue_wait_ms - t_proc)

        # Total response time = T_net + T_wait + T_proc + T_overhead
        t_resp = t_net + t_wait + t_proc + overhead_ms
        response_times.append(t_resp)

    completed = len(response_times)
    if completed > 0:
        sorted_times = sorted(response_times)
        mean_resp = sum(sorted_times) / completed
        p95_resp = sorted_times[int(0.95 * completed)]
        min_resp = sorted_times[0]
        max_resp = sorted_times[-1]
    else:
        mean_resp = p95_resp = min_resp = max_resp = 0.0

    return SimulationScenarioResult(
        scenario_name=scenario_name,
        algorithm=algorithm,
        total_tasks=len(tasks_with_time),
        completed_tasks=completed,
        failed_tasks=failed_tasks,
        mean_response_time_ms=round(mean_resp, 2),
        p95_response_time_ms=round(p95_resp, 2),
        min_response_time_ms=round(min_resp, 2),
        max_response_time_ms=round(max_resp, 2),
        node_distribution=node_distribution,
    )


def run_benchmark():
    random.seed(42)
    print("=" * 80)
    print("LFNS Comprehensive Simulation Benchmark")
    print("=" * 80)

    algorithms = ["LFNS", "NEAREST_NODE", "ROUND_ROBIN"]
    
    # 4 Scenarios from Table 3
    scenarios = [
        ("1. Medium Load", create_standard_network(), generate_workload(300, "medium")),
        ("1b. Heavy Load (Stress)", create_standard_network(), generate_workload(400, "heavy")),
        ("2. One Busy Node (F1 Overloaded)", None, generate_workload(300, "medium")),
        ("3. Slower Network (F1 Distorted)", None, generate_workload(300, "medium")),
        ("4. Node Disconnection (F1 Down)", None, generate_workload(300, "medium")),
    ]

    # Configure special network scenarios
    # Scenario 2: F1 has massive external queue
    busy_net = create_standard_network()
    busy_net["F1"].current_queue_wait_ms = 250.0  # F1 busy with hospital batch work
    scenarios[2] = ("2. One Busy Node (F1 Overloaded)", busy_net, scenarios[2][2])

    # Scenario 3: F1 network degraded
    slow_net = create_standard_network()
    slow_net["F1"].base_network_rtt_ms = 80.0  # Wi-Fi interference
    scenarios[3] = ("3. Slower Network (F1 Distorted)", slow_net, scenarios[3][2])

    # Scenario 4: F1 disconnected
    down_net = create_standard_network()
    down_net["F1"].status = NodeStatus.DISCONNECTED
    scenarios[4] = ("4. Node Disconnection (F1 Down)", down_net, scenarios[4][2])

    for sc_name, net, tasks in scenarios:
        print(f"\n>>> Scenario: {sc_name} (Tasks: {len(tasks)})")
        print(f"{'Algorithm':<15} | {'Mean (ms)':<10} | {'P95 (ms)':<10} | {'Completed':<10} | {'% Red. vs Nearest':<20} | {'Distribution'}")
        print("-" * 90)

        results = {}
        for algo in algorithms:
            res = run_single_simulation(sc_name, algo, tasks, net)
            results[algo] = res

        nearest_mean = results["NEAREST_NODE"].mean_response_time_ms
        for algo in algorithms:
            r = results[algo]
            if nearest_mean > 0 and r.mean_response_time_ms > 0:
                reduction = ((nearest_mean - r.mean_response_time_ms) / nearest_mean) * 100.0
                red_str = f"{reduction:+.1f}%"
            else:
                red_str = "N/A"

            dist_str = ", ".join([f"{k}:{v}" for k, v in r.node_distribution.items() if v > 0])
            print(f"{algo:<15} | {r.mean_response_time_ms:<10.1f} | {r.p95_response_time_ms:<10.1f} | {r.completed_tasks:<10} | {red_str:<20} | {dist_str}")

    print("\n" + "=" * 80)
    print("[OK] All 4 evaluation scenarios completed successfully.")


if __name__ == "__main__":
    run_benchmark()
