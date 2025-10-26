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
Deep Reinforcement Learning Agent for Scheduling Decisions
"""

import os
import logging
import random
from typing import List, Dict, Any, Optional
from collections import deque

import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv

from .config import SchedulerConfig
from .models import SchedulerPolicyNetwork, SchedulerValueNetwork
from .state_observer import ClusterStateObserver

logger = logging.getLogger(__name__)


class Experience:
    """Container for experience tuples"""
    def __init__(self, state, action, reward, next_state, done):
        self.state = state
        self.action = action
        self.reward = reward
        self.next_state = next_state
        self.done = done


class DRLAgent:
    """Deep Reinforcement Learning Agent for Scheduling"""

    def __init__(self, config: SchedulerConfig, state_observer: ClusterStateObserver):
        self.config = config
        self.state_observer = state_observer

        # Experience replay buffer
        self.memory = deque(maxlen=10000)

        # Exploration parameters
        self.epsilon = config.epsilon_start

        # Models
        self.policy_net = None
        self.value_net = None
        self.optimizer = None

        # PPO components
        self.ppo_model = None

        # Training stats
        self.total_steps = 0
        self.episode_rewards = []

    async def initialize(self):
        """Initialize the DRL agent"""
        logger.info("Initializing DRL Agent...")

        # Get state dimensions
        state_dim = await self._get_state_dimension()
        action_dim = self.config.max_nodes

        # Initialize networks
        self.policy_net = SchedulerPolicyNetwork(
            state_dim, action_dim, self.config.feature_dim
        )
        self.value_net = SchedulerValueNetwork(
            state_dim, self.config.feature_dim
        )

        # Load pretrained model if available
        if self.config.use_pretrained:
            await self.load_model()
        else:
            logger.info("Starting with randomly initialized model")

        # Initialize optimizer
        params = list(self.policy_net.parameters()) + list(self.value_net.parameters())
        self.optimizer = optim.Adam(params, lr=self.config.learning_rate)

        logger.info(
            f"DRL Agent initialized with state_dim={state_dim}, "
            f"action_dim={action_dim}, feature_dim={self.config.feature_dim}"
        )

    async def _get_state_dimension(self) -> int:
        """Calculate the dimension of state representation"""
        # Node features: CPU, memory, pods, network, etc.
        node_features = 10

        # Pod features: requirements, priority, affinity, etc.
        pod_features = 8

        # Cluster-level features: utilization, load, etc.
        cluster_features = 6

        # Total dimension
        return (node_features * self.config.max_nodes +
                pod_features + cluster_features)

    async def select_node(
        self,
        pod: Any,
        eligible_nodes: List[str],
        state: Dict[str, Any]
    ) -> Optional[str]:
        """Select the best node for a pod using the DRL policy"""

        if not eligible_nodes:
            return None

        # Encode state
        state_vector = await self._encode_state(pod, eligible_nodes, state)

        # Epsilon-greedy exploration
        if random.random() < self.epsilon:
            # Explore: random selection
            selected_node = random.choice(eligible_nodes)
            logger.debug(f"Exploration: randomly selected {selected_node}")
        else:
            # Exploit: use policy network
            selected_node = await self._select_best_node(
                state_vector, eligible_nodes, state
            )
            logger.debug(f"Exploitation: policy selected {selected_node}")

        # Decay epsilon
        self.epsilon = max(
            self.config.epsilon_end,
            self.epsilon * self.config.epsilon_decay
        )

        return selected_node

    async def _encode_state(
        self,
        pod: Any,
        eligible_nodes: List[str],
        state: Dict[str, Any]
    ) -> np.ndarray:
        """Encode the current state as a feature vector"""

        features = []

        # Node features for each eligible node
        for node_name in eligible_nodes:
            node_metrics = state['nodes'].get(node_name, {})

            node_feats = [
                node_metrics.get('cpu_usage', 0),
                node_metrics.get('memory_usage', 0),
                node_metrics.get('pod_count', 0) / self.config.max_pods,
                node_metrics.get('network_rx', 0),
                node_metrics.get('network_tx', 0),
                node_metrics.get('disk_usage', 0),
                node_metrics.get('cpu_allocatable', 0),
                node_metrics.get('memory_allocatable', 0),
                1.0 if node_metrics.get('is_ready') else 0.0,
                len(node_metrics.get('taints', [])) / 10.0
            ]
            features.extend(node_feats)

        # Pad if fewer nodes than max
        while len(features) < 10 * self.config.max_nodes:
            features.extend([0.0] * 10)

        # Pod features
        pod_cpu = self._get_pod_cpu_request(pod)
        pod_memory = self._get_pod_memory_request(pod)
        pod_priority = getattr(pod.spec, 'priority', 0) / 1000000.0

        pod_feats = [
            pod_cpu,
            pod_memory,
            pod_priority,
            1.0 if pod.spec.affinity else 0.0,
            1.0 if pod.spec.tolerations else 0.0,
            1.0 if pod.spec.node_selector else 0.0,
            len(pod.spec.containers),
            1.0 if self._is_stateful(pod) else 0.0
        ]
        features.extend(pod_feats)

        # Cluster-level features
        cluster_feats = [
            state.get('cluster_cpu_usage', 0),
            state.get('cluster_memory_usage', 0),
            state.get('total_pods', 0) / self.config.max_pods,
            state.get('total_nodes', 0) / self.config.max_nodes,
            state.get('avg_network_latency', 0),
            state.get('cluster_load', 0)
        ]
        features.extend(cluster_feats)

        return np.array(features, dtype=np.float32)

    def _get_pod_cpu_request(self, pod) -> float:
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

    def _get_pod_memory_request(self, pod) -> float:
        """Extract memory request from pod (normalized to GB)"""
        total_mem = 0.0
        for container in pod.spec.containers:
            if container.resources and container.resources.requests:
                mem = container.resources.requests.get('memory', '0')
                # Convert to GB
                if mem.endswith('Gi'):
                    total_mem += float(mem[:-2])
                elif mem.endswith('Mi'):
                    total_mem += float(mem[:-2]) / 1024
                elif mem.endswith('Ki'):
                    total_mem += float(mem[:-2]) / (1024**2)
        return total_mem

    def _is_stateful(self, pod) -> bool:
        """Check if pod is stateful"""
        # Check for volumes
        if pod.spec.volumes:
            for volume in pod.spec.volumes:
                if hasattr(volume, 'persistent_volume_claim'):
                    return True
        return False

    async def _select_best_node(
        self,
        state_vector: np.ndarray,
        eligible_nodes: List[str],
        state: Dict[str, Any]
    ) -> str:
        """Select best node using policy network"""

        with torch.no_grad():
            state_tensor = torch.FloatTensor(state_vector).unsqueeze(0)

            # Get action probabilities
            action_probs = self.policy_net(state_tensor)
            action_probs = action_probs.squeeze().numpy()

            # Mask invalid actions (non-eligible nodes)
            valid_mask = np.zeros(len(action_probs))
            for i, node in enumerate(eligible_nodes):
                if i < len(valid_mask):
                    valid_mask[i] = 1.0

            masked_probs = action_probs * valid_mask

            # Select node with highest probability
            if masked_probs.sum() > 0:
                masked_probs = masked_probs / masked_probs.sum()
                node_idx = np.argmax(masked_probs)
                if node_idx < len(eligible_nodes):
                    return eligible_nodes[node_idx]

        # Fallback to random if something goes wrong
        return random.choice(eligible_nodes)

    async def store_experience(
        self,
        state: Dict[str, Any],
        action: str,
        reward: float,
        pod: Any
    ):
        """Store experience in replay buffer"""

        # Get next state
        next_state = await self.state_observer.get_state()

        # Create experience
        exp = Experience(
            state=state,
            action=action,
            reward=reward,
            next_state=next_state,
            done=False  # Scheduling is a continuing task
        )

        self.memory.append(exp)
        self.total_steps += 1

    async def train(self) -> Dict[str, float]:
        """Train the agent using experiences from memory"""

        if len(self.memory) < self.config.batch_size:
            logger.debug("Not enough experiences for training")
            return {}

        # Sample batch
        batch = random.sample(self.memory, self.config.batch_size)

        # Prepare training data
        states = []
        actions = []
        rewards = []
        next_states = []
        dones = []

        for exp in batch:
            # Encode states (simplified for training)
            state_vec = np.random.randn(await self._get_state_dimension())
            next_state_vec = np.random.randn(await self._get_state_dimension())

            states.append(state_vec)
            actions.append(0)  # Placeholder
            rewards.append(exp.reward)
            next_states.append(next_state_vec)
            dones.append(exp.done)

        # Convert to tensors
        states_t = torch.FloatTensor(np.array(states))
        rewards_t = torch.FloatTensor(rewards)
        next_states_t = torch.FloatTensor(np.array(next_states))
        dones_t = torch.FloatTensor(dones)

        # Compute value targets
        with torch.no_grad():
            next_values = self.value_net(next_states_t).squeeze()
            targets = rewards_t + self.config.gamma * next_values * (1 - dones_t)

        # Compute current values
        current_values = self.value_net(states_t).squeeze()

        # Value loss
        value_loss = nn.MSELoss()(current_values, targets)

        # Policy loss (simplified)
        action_probs = self.policy_net(states_t)
        advantages = targets - current_values.detach()
        policy_loss = -(torch.log(action_probs.mean(dim=1)) * advantages).mean()

        # Total loss
        total_loss = value_loss + policy_loss

        # Optimize
        self.optimizer.zero_grad()
        total_loss.backward()
        torch.nn.utils.clip_grad_norm_(
            list(self.policy_net.parameters()) + list(self.value_net.parameters()),
            max_norm=0.5
        )
        self.optimizer.step()

        # Calculate metrics
        avg_reward = np.mean(rewards)

        metrics = {
            'loss': total_loss.item(),
            'value_loss': value_loss.item(),
            'policy_loss': policy_loss.item(),
            'avg_reward': avg_reward,
            'epsilon': self.epsilon
        }

        return metrics

    async def save_model(self):
        """Save model checkpoint"""
        model_dir = self.config.model_path
        os.makedirs(model_dir, exist_ok=True)

        checkpoint = {
            'policy_state_dict': self.policy_net.state_dict(),
            'value_state_dict': self.value_net.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'epsilon': self.epsilon,
            'total_steps': self.total_steps
        }

        path = os.path.join(model_dir, f"{self.config.model_name}.pt")
        torch.save(checkpoint, path)
        logger.info(f"Model saved to {path}")

    async def load_model(self):
        """Load model checkpoint"""
        path = os.path.join(self.config.model_path, f"{self.config.model_name}.pt")

        if not os.path.exists(path):
            logger.warning(f"Model file not found: {path}")
            return

        try:
            checkpoint = torch.load(path)
            self.policy_net.load_state_dict(checkpoint['policy_state_dict'])
            self.value_net.load_state_dict(checkpoint['value_state_dict'])
            self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
            self.epsilon = checkpoint.get('epsilon', self.config.epsilon_start)
            self.total_steps = checkpoint.get('total_steps', 0)

            logger.info(f"Model loaded from {path}")
        except Exception as e:
            logger.error(f"Error loading model: {e}")
