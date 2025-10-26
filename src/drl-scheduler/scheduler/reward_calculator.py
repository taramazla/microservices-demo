# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Reward Calculator for DRL Scheduler
"""

import logging
from typing import Dict, Any
import numpy as np

from .config import SchedulerConfig

logger = logging.getLogger(__name__)


class RewardCalculator:
    """
    Calculates rewards for scheduling decisions based on multiple objectives:
    - Resource utilization efficiency
    - Load balancing
    - Latency optimization
    - Affinity/anti-affinity compliance
    - Energy efficiency
    """

    def __init__(self, config: SchedulerConfig):
        self.config = config
        self.weights = config.reward_weights

    async def calculate_reward(
        self,
        pod: Any,
        selected_node: str,
        state: Dict[str, Any]
    ) -> float:
        """
        Calculate total reward for a scheduling decision

        Returns:
            float: Reward value (higher is better)
        """

        # Calculate individual reward components
        resource_reward = await self._resource_utilization_reward(
            pod, selected_node, state
        )

        load_balance_reward = await self._load_balance_reward(
            selected_node, state
        )

        latency_reward = await self._latency_reward(
            pod, selected_node, state
        )

        affinity_reward = await self._affinity_reward(
            pod, selected_node, state
        )

        energy_reward = await self._energy_efficiency_reward(
            selected_node, state
        )

        # Weighted combination
        total_reward = (
            self.weights['resource_utilization'] * resource_reward +
            self.weights['load_balance'] * load_balance_reward +
            self.weights['latency'] * latency_reward +
            self.weights['affinity'] * affinity_reward +
            self.weights['energy'] * energy_reward
        )

        logger.debug(
            f"Reward breakdown for {pod.metadata.name} -> {selected_node}: "
            f"resource={resource_reward:.3f}, load_balance={load_balance_reward:.3f}, "
            f"latency={latency_reward:.3f}, affinity={affinity_reward:.3f}, "
            f"energy={energy_reward:.3f}, total={total_reward:.3f}"
        )

        return total_reward

    async def _resource_utilization_reward(
        self,
        pod: Any,
        selected_node: str,
        state: Dict[str, Any]
    ) -> float:
        """
        Reward for efficient resource utilization

        Goals:
        - Maximize resource utilization without overcommitting
        - Prefer nodes with resources that closely match pod requirements
        - Avoid fragmentation
        """

        node_metrics = state['nodes'].get(selected_node, {})

        if not node_metrics:
            return 0.0

        # Get pod resource requirements
        pod_cpu = self._get_pod_cpu(pod)
        pod_memory = self._get_pod_memory(pod)

        # Node available resources
        node_cpu_available = (
            node_metrics['cpu_allocatable'] - node_metrics['cpu_used']
        )
        node_memory_available = (
            node_metrics['memory_allocatable'] - node_metrics['memory_used']
        )

        # Calculate utilization after scheduling
        cpu_util_after = (
            (node_metrics['cpu_used'] + pod_cpu) /
            node_metrics['cpu_allocatable']
        )
        memory_util_after = (
            (node_metrics['memory_used'] + pod_memory) /
            node_metrics['memory_allocatable']
        )

        # Reward for balanced utilization (target ~70-80%)
        target_utilization = 0.75
        cpu_deviation = abs(cpu_util_after - target_utilization)
        memory_deviation = abs(memory_util_after - target_utilization)

        utilization_score = 1.0 - (cpu_deviation + memory_deviation) / 2.0

        # Penalize if overcommitting
        if cpu_util_after > 0.95 or memory_util_after > 0.95:
            utilization_score *= 0.5

        # Bonus for fitting well (avoiding fragmentation)
        fit_score = 1.0 - abs(
            (pod_cpu / node_cpu_available) -
            (pod_memory / node_memory_available)
        )

        return (utilization_score * 0.7 + fit_score * 0.3)

    async def _load_balance_reward(
        self,
        selected_node: str,
        state: Dict[str, Any]
    ) -> float:
        """
        Reward for load balancing across nodes

        Goals:
        - Distribute workload evenly
        - Avoid hotspots
        - Maintain cluster stability
        """

        nodes = state['nodes']

        if len(nodes) < 2:
            return 1.0

        # Calculate load distribution
        cpu_usages = [n['cpu_usage'] for n in nodes.values()]
        memory_usages = [n['memory_usage'] for n in nodes.values()]

        # Standard deviation of usage (lower is better)
        cpu_std = np.std(cpu_usages)
        memory_std = np.std(memory_usages)

        # Selected node's position relative to mean
        avg_cpu = np.mean(cpu_usages)
        avg_memory = np.mean(memory_usages)

        selected_cpu = nodes[selected_node]['cpu_usage']
        selected_memory = nodes[selected_node]['memory_usage']

        # Reward scheduling on underutilized nodes
        cpu_balance_score = 1.0 - abs(selected_cpu - avg_cpu)
        memory_balance_score = 1.0 - abs(selected_memory - avg_memory)

        # Overall balance
        balance_score = (cpu_balance_score + memory_balance_score) / 2.0

        # Bonus for reducing variance
        variance_score = 1.0 - (cpu_std + memory_std) / 2.0

        return (balance_score * 0.6 + variance_score * 0.4)

    async def _latency_reward(
        self,
        pod: Any,
        selected_node: str,
        state: Dict[str, Any]
    ) -> float:
        """
        Reward for minimizing latency

        Goals:
        - Co-locate frequently communicating services
        - Minimize inter-node communication
        - Consider network topology
        """

        # Check for affinity preferences
        if not pod.spec.affinity:
            return 0.8  # Neutral score

        reward = 0.0
        count = 0

        # Pod affinity
        if pod.spec.affinity.pod_affinity:
            for term in (pod.spec.affinity.pod_affinity.preferred_during_scheduling_ignored_during_execution or []):
                # Check if preferred pods are on the selected node
                weight = term.weight / 100.0

                # Simplified: assume co-location is good
                reward += weight
                count += 1

        # Pod anti-affinity
        if pod.spec.affinity.pod_anti_affinity:
            for term in (pod.spec.affinity.pod_anti_affinity.preferred_during_scheduling_ignored_during_execution or []):
                # Check if anti-affinity pods are NOT on selected node
                weight = term.weight / 100.0

                # Simplified: assume separation is good
                reward += weight
                count += 1

        if count > 0:
            return reward / count
        else:
            return 0.8

    async def _affinity_reward(
        self,
        pod: Any,
        selected_node: str,
        state: Dict[str, Any]
    ) -> float:
        """
        Reward for respecting affinity/anti-affinity rules

        Goals:
        - Honor pod affinity preferences
        - Honor node affinity preferences
        - Respect topology spread constraints
        """

        reward = 1.0

        # Node affinity
        if pod.spec.affinity and pod.spec.affinity.node_affinity:
            node_affinity = pod.spec.affinity.node_affinity
            node_labels = state['nodes'][selected_node]['labels']

            # Check preferred terms
            if node_affinity.preferred_during_scheduling_ignored_during_execution:
                for term in node_affinity.preferred_during_scheduling_ignored_during_execution:
                    weight = term.weight / 100.0

                    # Check if node matches preference
                    matches = self._check_node_selector_term(
                        term.preference,
                        node_labels
                    )

                    if matches:
                        reward += weight * 0.5

        # Topology spread constraints
        if pod.spec.topology_spread_constraints:
            # Simplified: give bonus for spreading
            reward += 0.2

        return min(reward, 2.0) / 2.0  # Normalize to [0, 1]

    async def _energy_efficiency_reward(
        self,
        selected_node: str,
        state: Dict[str, Any]
    ) -> float:
        """
        Reward for energy efficiency

        Goals:
        - Consolidate workloads to reduce active nodes
        - Prefer nodes with better power efficiency
        - Enable node scaling down when possible
        """

        node_metrics = state['nodes'].get(selected_node, {})

        if not node_metrics:
            return 0.5

        # Prefer utilizing already-active nodes
        current_usage = node_metrics['cpu_usage']

        # Reward higher utilization (consolidation)
        if current_usage > 0.1:  # Node is already active
            consolidation_score = min(current_usage * 1.5, 1.0)
        else:  # Activating new node
            consolidation_score = 0.3

        # Prefer nodes with higher pod count (consolidation)
        pod_count_score = min(node_metrics['pod_count'] / 20.0, 1.0)

        return (consolidation_score * 0.7 + pod_count_score * 0.3)

    def _get_pod_cpu(self, pod) -> float:
        """Extract CPU request from pod"""
        total_cpu = 0.0
        for container in pod.spec.containers:
            if container.resources and container.resources.requests:
                cpu = container.resources.requests.get('cpu', '0')
                if cpu.endswith('m'):
                    total_cpu += float(cpu[:-1]) / 1000
                else:
                    total_cpu += float(cpu)
        return total_cpu

    def _get_pod_memory(self, pod) -> float:
        """Extract memory request from pod (in bytes)"""
        total_mem = 0.0
        for container in pod.spec.containers:
            if container.resources and container.resources.requests:
                mem = container.resources.requests.get('memory', '0')
                if mem.endswith('Gi'):
                    total_mem += float(mem[:-2]) * 1024**3
                elif mem.endswith('Mi'):
                    total_mem += float(mem[:-2]) * 1024**2
                elif mem.endswith('Ki'):
                    total_mem += float(mem[:-2]) * 1024
        return total_mem

    def _check_node_selector_term(
        self,
        selector_term,
        node_labels: Dict[str, str]
    ) -> bool:
        """Check if node labels match selector term"""
        # Simplified implementation
        if not hasattr(selector_term, 'match_expressions'):
            return True

        for expr in (selector_term.match_expressions or []):
            key = expr.key
            operator = expr.operator
            values = expr.values or []

            node_value = node_labels.get(key)

            if operator == "In":
                if node_value not in values:
                    return False
            elif operator == "NotIn":
                if node_value in values:
                    return False
            elif operator == "Exists":
                if key not in node_labels:
                    return False
            elif operator == "DoesNotExist":
                if key in node_labels:
                    return False

        return True
