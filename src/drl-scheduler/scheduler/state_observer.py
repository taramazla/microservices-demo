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
Cluster State Observer for collecting metrics and state information
"""

import asyncio
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta
from collections import defaultdict

from kubernetes import client
from kubernetes.client.rest import ApiException

from .config import SchedulerConfig

logger = logging.getLogger(__name__)


class ClusterStateObserver:
    """Observes and tracks cluster state for scheduling decisions"""

    def __init__(self, v1_api: client.CoreV1Api, config: SchedulerConfig):
        self.v1 = v1_api
        self.config = config

        # State cache
        self.node_metrics = {}
        self.pod_metrics = {}
        self.cluster_state = {}

        # Metrics collection
        self.metrics_history = defaultdict(list)
        self.last_update = None

        # Background task
        self.update_task = None

    async def initialize(self):
        """Initialize the state observer"""
        logger.info("Initializing cluster state observer...")

        # Initial state collection
        await self.update_state()

        # Start background update task
        self.update_task = asyncio.create_task(self._periodic_update())

        logger.info("Cluster state observer initialized")

    async def _periodic_update(self):
        """Periodically update cluster state"""
        while True:
            try:
                await asyncio.sleep(self.config.metrics_interval)
                await self.update_state()
            except Exception as e:
                logger.error(f"Error in periodic update: {e}")

    async def update_state(self):
        """Update the complete cluster state"""
        try:
            # Collect node metrics
            await self._collect_node_metrics()

            # Collect pod metrics
            await self._collect_pod_metrics()

            # Calculate cluster-level metrics
            await self._calculate_cluster_metrics()

            self.last_update = datetime.now()

        except Exception as e:
            logger.error(f"Error updating state: {e}")

    async def _collect_node_metrics(self):
        """Collect metrics for all nodes"""
        try:
            nodes = self.v1.list_node()

            for node in nodes.items:
                node_name = node.metadata.name

                # Get node status
                status = node.status

                # Extract allocatable resources
                allocatable = status.allocatable or {}

                # Get current capacity
                capacity = status.capacity or {}

                # Calculate usage (simplified - in production use Metrics API)
                cpu_allocatable = self._parse_cpu(allocatable.get('cpu', '0'))
                memory_allocatable = self._parse_memory(allocatable.get('memory', '0'))

                # Get pods on this node
                pods = self.v1.list_pod_for_all_namespaces(
                    field_selector=f'spec.nodeName={node_name}'
                )

                # Calculate resource usage
                cpu_used = 0.0
                memory_used = 0.0

                for pod in pods.items:
                    for container in pod.spec.containers:
                        if container.resources and container.resources.requests:
                            requests = container.resources.requests
                            cpu_used += self._parse_cpu(requests.get('cpu', '0'))
                            memory_used += self._parse_memory(requests.get('memory', '0'))

                # Node metrics
                self.node_metrics[node_name] = {
                    'cpu_allocatable': cpu_allocatable,
                    'memory_allocatable': memory_allocatable,
                    'cpu_used': cpu_used,
                    'memory_used': memory_used,
                    'cpu_usage': cpu_used / cpu_allocatable if cpu_allocatable > 0 else 0,
                    'memory_usage': memory_used / memory_allocatable if memory_allocatable > 0 else 0,
                    'pod_count': len(pods.items),
                    'is_ready': self._is_node_ready(node),
                    'taints': node.spec.taints or [],
                    'labels': node.metadata.labels or {},
                    'network_rx': 0.0,  # Placeholder - use metrics server
                    'network_tx': 0.0,  # Placeholder
                    'disk_usage': 0.0,  # Placeholder
                    'timestamp': datetime.now()
                }

                # Store in history
                self.metrics_history[f'node_{node_name}_cpu'].append({
                    'timestamp': datetime.now(),
                    'value': cpu_used / cpu_allocatable if cpu_allocatable > 0 else 0
                })

                # Trim history
                self._trim_history(f'node_{node_name}_cpu')

        except ApiException as e:
            logger.error(f"Error collecting node metrics: {e}")

    async def _collect_pod_metrics(self):
        """Collect metrics for all pods"""
        try:
            pods = self.v1.list_pod_for_all_namespaces()

            for pod in pods.items:
                pod_key = f"{pod.metadata.namespace}/{pod.metadata.name}"

                # Pod resource requests
                cpu_request = 0.0
                memory_request = 0.0

                for container in pod.spec.containers:
                    if container.resources and container.resources.requests:
                        requests = container.resources.requests
                        cpu_request += self._parse_cpu(requests.get('cpu', '0'))
                        memory_request += self._parse_memory(requests.get('memory', '0'))

                self.pod_metrics[pod_key] = {
                    'cpu_request': cpu_request,
                    'memory_request': memory_request,
                    'phase': pod.status.phase,
                    'node': pod.spec.node_name,
                    'priority': getattr(pod.spec, 'priority', 0),
                    'qos_class': pod.status.qos_class,
                    'timestamp': datetime.now()
                }

        except ApiException as e:
            logger.error(f"Error collecting pod metrics: {e}")

    async def _calculate_cluster_metrics(self):
        """Calculate cluster-level aggregated metrics"""

        if not self.node_metrics:
            return

        # Aggregate node metrics
        total_cpu = sum(n['cpu_allocatable'] for n in self.node_metrics.values())
        total_memory = sum(n['memory_allocatable'] for n in self.node_metrics.values())
        used_cpu = sum(n['cpu_used'] for n in self.node_metrics.values())
        used_memory = sum(n['memory_used'] for n in self.node_metrics.values())

        total_pods = sum(n['pod_count'] for n in self.node_metrics.values())
        total_nodes = len(self.node_metrics)
        ready_nodes = sum(1 for n in self.node_metrics.values() if n['is_ready'])

        # Calculate load balance variance
        if total_nodes > 0:
            avg_cpu = used_cpu / total_nodes
            cpu_variance = sum(
                (n['cpu_used'] - avg_cpu) ** 2
                for n in self.node_metrics.values()
            ) / total_nodes
            load_balance_score = 1.0 / (1.0 + cpu_variance)
        else:
            load_balance_score = 0.0

        self.cluster_state = {
            'total_cpu': total_cpu,
            'total_memory': total_memory,
            'used_cpu': used_cpu,
            'used_memory': used_memory,
            'cluster_cpu_usage': used_cpu / total_cpu if total_cpu > 0 else 0,
            'cluster_memory_usage': used_memory / total_memory if total_memory > 0 else 0,
            'total_pods': total_pods,
            'total_nodes': total_nodes,
            'ready_nodes': ready_nodes,
            'load_balance_score': load_balance_score,
            'avg_network_latency': 0.0,  # Placeholder
            'cluster_load': used_cpu / total_cpu if total_cpu > 0 else 0,
            'timestamp': datetime.now()
        }

    async def get_state(self) -> Dict[str, Any]:
        """Get the current cluster state"""
        return {
            'nodes': self.node_metrics.copy(),
            'pods': self.pod_metrics.copy(),
            **self.cluster_state
        }

    async def get_node_metrics(self, node_name: str) -> Dict[str, Any]:
        """Get metrics for a specific node"""
        return self.node_metrics.get(node_name, {})

    async def get_pod_metrics(self, namespace: str, pod_name: str) -> Dict[str, Any]:
        """Get metrics for a specific pod"""
        pod_key = f"{namespace}/{pod_name}"
        return self.pod_metrics.get(pod_key, {})

    def _is_node_ready(self, node) -> bool:
        """Check if node is ready"""
        if not node.status or not node.status.conditions:
            return False

        for condition in node.status.conditions:
            if condition.type == "Ready" and condition.status == "True":
                return True
        return False

    def _parse_cpu(self, cpu_str: str) -> float:
        """Parse CPU string to float (in cores)"""
        if not cpu_str:
            return 0.0
        if cpu_str.endswith('m'):
            return float(cpu_str[:-1]) / 1000
        return float(cpu_str)

    def _parse_memory(self, mem_str: str) -> float:
        """Parse memory string to float (in bytes)"""
        if not mem_str:
            return 0.0

        units = {
            'Ki': 1024,
            'Mi': 1024**2,
            'Gi': 1024**3,
            'Ti': 1024**4,
            'K': 1000,
            'M': 1000**2,
            'G': 1000**3,
            'T': 1000**4
        }

        for unit, multiplier in units.items():
            if mem_str.endswith(unit):
                return float(mem_str[:-len(unit)]) * multiplier

        return float(mem_str)

    def _trim_history(self, key: str):
        """Trim metrics history to configured window"""
        cutoff = datetime.now() - timedelta(seconds=self.config.metrics_window)

        if key in self.metrics_history:
            self.metrics_history[key] = [
                m for m in self.metrics_history[key]
                if m['timestamp'] > cutoff
            ]

    async def shutdown(self):
        """Shutdown the observer"""
        if self.update_task:
            self.update_task.cancel()
