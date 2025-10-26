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
Kubernetes Scheduler with DRL Agent Integration
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import urllib.request

from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException

from .config import SchedulerConfig
from .state_observer import ClusterStateObserver
from .drl_agent import DRLAgent
from .reward_calculator import RewardCalculator
from monitoring.metrics import SchedulerMetrics

logger = logging.getLogger(__name__)


class DRLScheduler:
    """DRL-Enhanced Kubernetes Scheduler"""

    def __init__(self, scheduler_config: SchedulerConfig):
        self.config = scheduler_config
        self.v1 = None
        self.state_observer = None
        self.drl_agent = None
        self.reward_calculator = None
        self.metrics = SchedulerMetrics()

        self.scheduled_pods = 0
        self.failed_schedules = 0
        self.training_episodes = 0

    async def initialize(self):
        """Initialize the scheduler components"""
        logger.info("Initializing DRL Scheduler...")

        # Load Kubernetes config
        try:
            if self.config.in_cluster:
                config.load_incluster_config()
                logger.info("Loaded in-cluster Kubernetes config")
            else:
                config.load_kube_config(self.config.kubeconfig_path)
                logger.info("Loaded kubeconfig from file")
        except Exception as e:
            logger.error(f"Failed to load Kubernetes config: {e}")
            raise

        self.v1 = client.CoreV1Api()

        # Initialize components
        self.state_observer = ClusterStateObserver(self.v1, self.config)
        await self.state_observer.initialize()
        logger.info("Cluster state observer initialized")

        self.reward_calculator = RewardCalculator(self.config)
        logger.info("Reward calculator initialized")

        self.drl_agent = DRLAgent(self.config, self.state_observer)
        await self.drl_agent.initialize()
        logger.info("DRL agent initialized")

        logger.info("DRL Scheduler initialization complete")

    async def run(self):
        """Main scheduling loop"""
        logger.info("Starting scheduling loop...")

        w = watch.Watch()

        try:
            async for event in self._watch_pending_pods(w):
                if event['type'] in ['ADDED', 'MODIFIED']:
                    pod = event['object']

                    # Check if pod needs scheduling
                    if self._needs_scheduling(pod):
                        await self._schedule_pod(pod)

        except Exception as e:
            logger.error(f"Error in scheduling loop: {e}", exc_info=True)
            raise

    async def _watch_pending_pods(self, w):
        """Watch for pending pods that need scheduling"""
        field_selector = f"spec.schedulerName={self.config.scheduler_name},status.phase=Pending"

        while True:
            try:
                stream = w.stream(
                    self.v1.list_pod_for_all_namespaces,
                    field_selector=field_selector,
                    timeout_seconds=60
                )

                for event in stream:
                    yield event

            except ApiException as e:
                if e.status == 410:  # Resource version expired
                    logger.warning("Watch expired, restarting...")
                    continue
                else:
                    logger.error(f"API exception in watch: {e}")
                    await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Error watching pods: {e}")
                await asyncio.sleep(5)

    def _needs_scheduling(self, pod) -> bool:
        """Check if a pod needs scheduling"""
        # Pod is pending and has no node assignment
        if pod.status.phase != "Pending":
            return False

        if pod.spec.node_name:
            return False

        # Check if scheduler name matches
        scheduler_name = pod.spec.scheduler_name or "default-scheduler"
        if scheduler_name != self.config.scheduler_name:
            return False

        return True

    async def _schedule_pod(self, pod):
        """Schedule a pod using the DRL agent"""
        pod_name = pod.metadata.name
        namespace = pod.metadata.namespace

        logger.info(f"Scheduling pod {namespace}/{pod_name}")
        start_time = datetime.now()

        try:
            # Get current cluster state
            state = await self.state_observer.get_state()

            # Get eligible nodes
            nodes = await self._get_eligible_nodes(pod)
            if not nodes:
                logger.warning(f"No eligible nodes for pod {pod_name}")
                self.failed_schedules += 1
                self.metrics.record_failed_schedule(pod_name, "no_eligible_nodes")
                return

            # Use DRL agent to select best node
            selected_node = await self.drl_agent.select_node(
                pod, nodes, state
            )

            if not selected_node:
                logger.warning(f"Agent could not select node for pod {pod_name}")
                self.failed_schedules += 1
                self.metrics.record_failed_schedule(pod_name, "no_node_selected")
                return

            # Bind pod to node
            await self._bind_pod_to_node(pod, selected_node)

            # Calculate reward
            reward = await self.reward_calculator.calculate_reward(
                pod, selected_node, state
            )

            # Store experience for training
            if self.config.enable_training:
                await self.drl_agent.store_experience(
                    state, selected_node, reward, pod
                )

            # Update metrics
            duration = (datetime.now() - start_time).total_seconds()
            self.scheduled_pods += 1
            self.metrics.record_successful_schedule(
                pod_name, selected_node, duration, reward
            )

            logger.info(
                f"Successfully scheduled {pod_name} to {selected_node} "
                f"(reward: {reward:.3f}, duration: {duration:.3f}s)"
            )

            # Periodic training
            if (self.config.enable_training and
                self.scheduled_pods % self.config.training_interval == 0):
                await self._train_agent()

        except Exception as e:
            logger.error(f"Error scheduling pod {pod_name}: {e}", exc_info=True)
            self.failed_schedules += 1
            self.metrics.record_failed_schedule(pod_name, str(e))

    async def _get_eligible_nodes(self, pod) -> List[str]:
        """Get list of nodes eligible for the pod"""
        try:
            nodes = self.v1.list_node()
            eligible = []

            for node in nodes.items:
                # Check node is ready
                if not self._is_node_ready(node):
                    continue

                # Check taints and tolerations
                if self.config.enable_taints:
                    if not self._check_tolerations(pod, node):
                        continue

                # Check resource requirements
                if not await self._check_resources(pod, node):
                    continue

                # Check node selectors
                if not self._check_node_selectors(pod, node):
                    continue

                eligible.append(node.metadata.name)

            return eligible

        except Exception as e:
            logger.error(f"Error getting eligible nodes: {e}")
            return []

    def _is_node_ready(self, node) -> bool:
        """Check if node is ready"""
        if not node.status or not node.status.conditions:
            return False

        for condition in node.status.conditions:
            if condition.type == "Ready" and condition.status == "True":
                return True
        return False

    def _check_tolerations(self, pod, node) -> bool:
        """Check if pod tolerates node taints"""
        if not node.spec.taints:
            return True

        pod_tolerations = pod.spec.tolerations or []

        for taint in node.spec.taints:
            tolerated = False
            for toleration in pod_tolerations:
                if (toleration.key == taint.key and
                    (toleration.operator == "Exists" or
                     toleration.value == taint.value)):
                    tolerated = True
                    break
            if not tolerated and taint.effect in ["NoSchedule", "NoExecute"]:
                return False

        return True

    async def _check_resources(self, pod, node) -> bool:
        """Check if node has sufficient resources"""
        # Get node allocatable resources
        allocatable = node.status.allocatable

        if not allocatable:
            return False

        # Get current usage
        node_metrics = await self.state_observer.get_node_metrics(
            node.metadata.name
        )

        # Check each container's requirements
        for container in pod.spec.containers:
            if container.resources and container.resources.requests:
                requests = container.resources.requests

                # Check CPU
                if 'cpu' in requests:
                    required_cpu = self._parse_cpu(requests['cpu'])
                    available_cpu = (
                        self._parse_cpu(allocatable.get('cpu', '0')) -
                        node_metrics.get('cpu_used', 0)
                    )
                    if required_cpu > available_cpu:
                        return False

                # Check memory
                if 'memory' in requests:
                    required_mem = self._parse_memory(requests['memory'])
                    available_mem = (
                        self._parse_memory(allocatable.get('memory', '0')) -
                        node_metrics.get('memory_used', 0)
                    )
                    if required_mem > available_mem:
                        return False

        return True

    def _check_node_selectors(self, pod, node) -> bool:
        """Check if pod's node selector matches node labels"""
        if not pod.spec.node_selector:
            return True

        node_labels = node.metadata.labels or {}

        for key, value in pod.spec.node_selector.items():
            if node_labels.get(key) != value:
                return False

        return True

    async def _bind_pod_to_node(self, pod, node_name: str):
        """Bind a pod to a specific node using direct REST API call"""
        binding = {
            "apiVersion": "v1",
            "kind": "Binding",
            "metadata": {
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace
            },
            "target": {
                "apiVersion": "v1",
                "kind": "Node",
                "name": node_name
            }
        }

        try:
            # Get API server URL and auth token
            api_config = client.Configuration().get_default_copy()
            api_host = api_config.host

            # Use service account token for authentication
            with open('/var/run/secrets/kubernetes.io/serviceaccount/token', 'r') as f:
                token = f.read()

            # Create binding via REST API
            url = f"{api_host}/api/v1/namespaces/{pod.metadata.namespace}/pods/{pod.metadata.name}/binding"
            req = urllib.request.Request(
                url,
                data=json.dumps(binding).encode('utf-8'),
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json'
                },
                method='POST'
            )

            # Disable SSL verification for self-signed certs
            import ssl
            context = ssl._create_unverified_context()

            with urllib.request.urlopen(req, context=context) as response:
                logger.info(f"Successfully scheduled pod {pod.metadata.namespace}/{pod.metadata.name} to node {node_name}")
                self.scheduled_pods += 1

        except Exception as e:
            logger.error(f"Failed to bind pod {pod.metadata.name} to node {node_name}: {e}")
            self.failed_schedules += 1
            raise

    async def _train_agent(self):
        """Train the DRL agent"""
        logger.info("Starting training episode...")

        try:
            metrics = await self.drl_agent.train()
            self.training_episodes += 1

            logger.info(
                f"Training episode {self.training_episodes} complete: "
                f"loss={metrics.get('loss', 0):.4f}, "
                f"avg_reward={metrics.get('avg_reward', 0):.4f}"
            )

            self.metrics.record_training_metrics(metrics)

        except Exception as e:
            logger.error(f"Error during training: {e}", exc_info=True)

    def _parse_cpu(self, cpu_str: str) -> float:
        """Parse CPU string to float (in cores)"""
        if cpu_str.endswith('m'):
            return float(cpu_str[:-1]) / 1000
        return float(cpu_str)

    def _parse_memory(self, mem_str: str) -> float:
        """Parse memory string to float (in bytes)"""
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

    async def shutdown(self):
        """Gracefully shutdown the scheduler"""
        logger.info("Shutting down scheduler...")

        if self.drl_agent:
            await self.drl_agent.save_model()

        logger.info("Scheduler shutdown complete")
