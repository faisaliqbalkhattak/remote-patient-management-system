"""
Data models and entities for the LFNS Health Tracking System.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Any
import time


class TaskType(str, Enum):
    ECG_ANALYSIS = "ECG_ANALYSIS"
    PULSE_SPO2_PROCESS = "PULSE_SPO2_PROCESS"
    NIBP_TRENDING = "NIBP_TRENDING"
    VITALS_FUSION = "VITALS_FUSION"


class NodeStatus(str, Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    OVERLOADED = "OVERLOADED"


@dataclass
class HealthTask:
    task_id: str
    task_type: TaskType
    payload_size_bytes: int
    required_memory_mb: int
    compute_units: float  # Nominal computational requirement
    created_at_ms: float = field(default_factory=lambda: time.time() * 1000.0)
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FogNode:
    node_id: str
    name: str
    status: NodeStatus
    is_authorized: bool
    supported_tasks: List[TaskType]
    base_network_rtt_ms: float
    compute_capacity_units_per_ms: float
    total_memory_mb: int
    available_memory_mb: int
    communication_cost_score: float = 1.0  # Tiebreaker: lower is better
    current_queue_wait_ms: float = 0.0
    active_tasks: List[HealthTask] = field(default_factory=list)

    def is_eligible(self, task: HealthTask) -> bool:
        """Checks connection status, authorization, task compatibility, and memory."""
        if self.status != NodeStatus.CONNECTED:
            return False
        if not self.is_authorized:
            return False
        if task.task_type not in self.supported_tasks:
            return False
        if self.available_memory_mb < task.required_memory_mb:
            return False
        return True

    def calculate_processing_time(self, task: HealthTask) -> float:
        """T_processing = compute_units / compute_capacity."""
        if self.compute_capacity_units_per_ms <= 0:
            return 999999.0
        return task.compute_units / self.compute_capacity_units_per_ms


@dataclass
class NodeEstimate:
    node_id: str
    t_network: float
    t_queue: float
    t_processing: float
    t_total_estimated: float
    communication_cost: float


@dataclass
class SelectionResult:
    selected_node_id: Optional[str]
    estimates: Dict[str, NodeEstimate]
    selection_overhead_ms: float
    algorithm: str
    is_successful: bool
    failure_reason: Optional[str] = None


@dataclass
class ExecutionResult:
    task_id: str
    node_id: str
    algorithm: str
    t_device_ms: float
    t_overhead_ms: float
    t_network_ms: float
    t_queue_ms: float
    t_processing_ms: float
    t_total_response_ms: float
    timestamp_completed: float


@dataclass
class SimulationScenarioResult:
    scenario_name: str
    algorithm: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    mean_response_time_ms: float
    p95_response_time_ms: float
    min_response_time_ms: float
    max_response_time_ms: float
    node_distribution: Dict[str, int]
