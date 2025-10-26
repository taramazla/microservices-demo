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
Metrics collection and monitoring
"""

import time
from typing import Dict, Any
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry
import logging

logger = logging.getLogger(__name__)


# Global registry
REGISTRY = CollectorRegistry()

# Scheduling metrics
SCHEDULE_ATTEMPTS = Counter(
    'drl_scheduler_schedule_attempts_total',
    'Total number of scheduling attempts',
    ['status'],  # success, failed
    registry=REGISTRY
)

SCHEDULE_DURATION = Histogram(
    'drl_scheduler_schedule_duration_seconds',
    'Time spent scheduling a pod',
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0],
    registry=REGISTRY
)

SCHEDULE_REWARD = Histogram(
    'drl_scheduler_schedule_reward',
    'Reward value for scheduling decisions',
    buckets=[-1.0, -0.5, 0.0, 0.5, 0.75, 0.9, 1.0],
    registry=REGISTRY
)

# DRL Agent metrics
TRAINING_EPISODES = Counter(
    'drl_scheduler_training_episodes_total',
    'Total number of training episodes',
    registry=REGISTRY
)

TRAINING_LOSS = Gauge(
    'drl_scheduler_training_loss',
    'Current training loss',
    registry=REGISTRY
)

EXPLORATION_RATE = Gauge(
    'drl_scheduler_exploration_rate',
    'Current epsilon (exploration rate)',
    registry=REGISTRY
)

EXPERIENCE_BUFFER_SIZE = Gauge(
    'drl_scheduler_experience_buffer_size',
    'Number of experiences in replay buffer',
    registry=REGISTRY
)

# Cluster metrics
CLUSTER_CPU_USAGE = Gauge(
    'drl_scheduler_cluster_cpu_usage',
    'Overall cluster CPU usage',
    registry=REGISTRY
)

CLUSTER_MEMORY_USAGE = Gauge(
    'drl_scheduler_cluster_memory_usage',
    'Overall cluster memory usage',
    registry=REGISTRY
)

NODE_COUNT = Gauge(
    'drl_scheduler_node_count',
    'Number of nodes in cluster',
    ['state'],  # ready, not_ready
    registry=REGISTRY
)

POD_COUNT = Gauge(
    'drl_scheduler_pod_count',
    'Number of pods in cluster',
    registry=REGISTRY
)


class SchedulerMetrics:
    """Wrapper for scheduler metrics"""

    def __init__(self):
        self.registry = REGISTRY

    def record_successful_schedule(
        self,
        pod_name: str,
        node_name: str,
        duration: float,
        reward: float
    ):
        """Record a successful scheduling decision"""
        SCHEDULE_ATTEMPTS.labels(status='success').inc()
        SCHEDULE_DURATION.observe(duration)
        SCHEDULE_REWARD.observe(reward)

        logger.info(
            f"Metrics: Scheduled {pod_name} to {node_name} "
            f"(duration={duration:.3f}s, reward={reward:.3f})"
        )

    def record_failed_schedule(self, pod_name: str, reason: str):
        """Record a failed scheduling attempt"""
        SCHEDULE_ATTEMPTS.labels(status='failed').inc()
        logger.warning(f"Metrics: Failed to schedule {pod_name}: {reason}")

    def record_training_metrics(self, metrics: Dict[str, Any]):
        """Record training metrics"""
        TRAINING_EPISODES.inc()

        if 'loss' in metrics:
            TRAINING_LOSS.set(metrics['loss'])

        if 'epsilon' in metrics:
            EXPLORATION_RATE.set(metrics['epsilon'])

        logger.info(f"Metrics: Training completed with metrics: {metrics}")

    def update_cluster_metrics(self, state: Dict[str, Any]):
        """Update cluster-level metrics"""
        CLUSTER_CPU_USAGE.set(state.get('cluster_cpu_usage', 0))
        CLUSTER_MEMORY_USAGE.set(state.get('cluster_memory_usage', 0))

        total_nodes = state.get('total_nodes', 0)
        ready_nodes = state.get('ready_nodes', 0)

        NODE_COUNT.labels(state='ready').set(ready_nodes)
        NODE_COUNT.labels(state='not_ready').set(total_nodes - ready_nodes)

        POD_COUNT.set(state.get('total_pods', 0))

    def update_buffer_size(self, size: int):
        """Update experience buffer size"""
        EXPERIENCE_BUFFER_SIZE.set(size)


def setup_metrics():
    """Setup metrics collection"""
    logger.info("Metrics collection initialized")
    return REGISTRY
