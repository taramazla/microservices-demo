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
Neural Network Models for DRL Scheduler
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple


class SchedulerPolicyNetwork(nn.Module):
    """Policy network for action selection"""

    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int = 128):
        super(SchedulerPolicyNetwork, self).__init__()

        self.state_dim = state_dim
        self.action_dim = action_dim

        # Encoder for state representation
        self.encoder = nn.Sequential(
            nn.Linear(state_dim, hidden_dim * 2),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim * 2),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
        )

        # Policy head
        self.policy_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, action_dim),
            nn.Softmax(dim=-1)
        )

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        """Forward pass to get action probabilities"""
        features = self.encoder(state)
        action_probs = self.policy_head(features)
        return action_probs


class SchedulerValueNetwork(nn.Module):
    """Value network for state value estimation"""

    def __init__(self, state_dim: int, hidden_dim: int = 128):
        super(SchedulerValueNetwork, self).__init__()

        self.state_dim = state_dim

        # Encoder for state representation
        self.encoder = nn.Sequential(
            nn.Linear(state_dim, hidden_dim * 2),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim * 2),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
        )

        # Value head
        self.value_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1)
        )

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        """Forward pass to get state value"""
        features = self.encoder(state)
        value = self.value_head(features)
        return value


class AttentionSchedulerNetwork(nn.Module):
    """
    Advanced scheduler network using attention mechanism
    for better node-pod matching
    """

    def __init__(self, node_dim: int, pod_dim: int, hidden_dim: int = 128):
        super(AttentionSchedulerNetwork, self).__init__()

        self.node_dim = node_dim
        self.pod_dim = pod_dim
        self.hidden_dim = hidden_dim

        # Node encoder
        self.node_encoder = nn.Sequential(
            nn.Linear(node_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim)
        )

        # Pod encoder
        self.pod_encoder = nn.Sequential(
            nn.Linear(pod_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim)
        )

        # Multi-head attention
        self.attention = nn.MultiheadAttention(
            embed_dim=hidden_dim,
            num_heads=4,
            batch_first=True
        )

        # Output layer
        self.output = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1)
        )

    def forward(
        self,
        node_features: torch.Tensor,
        pod_features: torch.Tensor
    ) -> torch.Tensor:
        """
        Forward pass with attention

        Args:
            node_features: [batch, num_nodes, node_dim]
            pod_features: [batch, pod_dim]

        Returns:
            scores: [batch, num_nodes] - scheduling scores for each node
        """
        batch_size, num_nodes, _ = node_features.shape

        # Encode nodes
        node_encoded = self.node_encoder(node_features)  # [batch, num_nodes, hidden]

        # Encode pod
        pod_encoded = self.pod_encoder(pod_features)  # [batch, hidden]
        pod_encoded = pod_encoded.unsqueeze(1)  # [batch, 1, hidden]

        # Attention: pod queries node features
        attn_output, _ = self.attention(
            query=pod_encoded,
            key=node_encoded,
            value=node_encoded
        )  # [batch, 1, hidden]

        # Compute compatibility scores
        attn_output = attn_output.squeeze(1)  # [batch, hidden]

        # Expand for node-wise scoring
        attn_expanded = attn_output.unsqueeze(1).expand(-1, num_nodes, -1)

        # Combine with node features
        combined = node_encoded + attn_expanded

        # Output scores
        scores = self.output(combined).squeeze(-1)  # [batch, num_nodes]

        # Apply softmax
        scores = F.softmax(scores, dim=-1)

        return scores


class GraphNeuralScheduler(nn.Module):
    """
    Graph Neural Network for modeling cluster topology
    and pod-node relationships
    """

    def __init__(self, node_dim: int, edge_dim: int, hidden_dim: int = 128):
        super(GraphNeuralScheduler, self).__init__()

        self.node_dim = node_dim
        self.edge_dim = edge_dim
        self.hidden_dim = hidden_dim

        # Node embedding
        self.node_embed = nn.Linear(node_dim, hidden_dim)

        # Edge embedding
        self.edge_embed = nn.Linear(edge_dim, hidden_dim)

        # Graph convolution layers
        self.conv1 = nn.Linear(hidden_dim * 2, hidden_dim)
        self.conv2 = nn.Linear(hidden_dim * 2, hidden_dim)

        # Output
        self.output = nn.Linear(hidden_dim, 1)

    def forward(
        self,
        node_features: torch.Tensor,
        edge_index: torch.Tensor,
        edge_features: torch.Tensor
    ) -> torch.Tensor:
        """
        Forward pass through GNN

        Args:
            node_features: [num_nodes, node_dim]
            edge_index: [2, num_edges] - connectivity
            edge_features: [num_edges, edge_dim]

        Returns:
            node_scores: [num_nodes] - scheduling scores
        """
        num_nodes = node_features.shape[0]

        # Embed nodes
        x = F.relu(self.node_embed(node_features))  # [num_nodes, hidden]

        # Embed edges
        edge_attr = F.relu(self.edge_embed(edge_features))  # [num_edges, hidden]

        # First graph convolution
        x = self._graph_conv(x, edge_index, edge_attr, self.conv1)

        # Second graph convolution
        x = self._graph_conv(x, edge_index, edge_attr, self.conv2)

        # Output scores
        scores = self.output(x).squeeze(-1)  # [num_nodes]

        return F.softmax(scores, dim=0)

    def _graph_conv(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        edge_attr: torch.Tensor,
        conv_layer: nn.Module
    ) -> torch.Tensor:
        """Apply graph convolution"""

        num_nodes = x.shape[0]

        # Aggregate messages from neighbors
        row, col = edge_index

        # Message passing
        messages = torch.zeros_like(x)
        for i, (src, dst) in enumerate(zip(row, col)):
            message = torch.cat([x[src], edge_attr[i]], dim=-1)
            messages[dst] += message

        # Apply convolution
        x = F.relu(conv_layer(messages))

        return x
