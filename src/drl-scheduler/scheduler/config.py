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
Configuration for DRL Scheduler
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class SchedulerConfig:
    """Configuration for the DRL-enhanced scheduler"""

    # Scheduler settings
    scheduler_name: str = "drl-scheduler"
    namespace: str = os.getenv("NAMESPACE", "default")
    polling_interval: float = float(os.getenv("POLLING_INTERVAL", "2.0"))

    # DRL Model settings
    model_path: str = os.getenv("MODEL_PATH", "/app/models")
    model_name: str = os.getenv("MODEL_NAME", "ppo_scheduler")
    use_pretrained: bool = os.getenv("USE_PRETRAINED", "false").lower() == "true"

    # Training settings
    enable_training: bool = os.getenv("ENABLE_TRAINING", "true").lower() == "true"
    training_interval: int = int(os.getenv("TRAINING_INTERVAL", "100"))
    batch_size: int = int(os.getenv("BATCH_SIZE", "64"))
    learning_rate: float = float(os.getenv("LEARNING_RATE", "0.0003"))
    gamma: float = float(os.getenv("GAMMA", "0.99"))

    # State space settings
    max_nodes: int = int(os.getenv("MAX_NODES", "100"))
    max_pods: int = int(os.getenv("MAX_PODS", "1000"))
    feature_dim: int = int(os.getenv("FEATURE_DIM", "128"))

    # Reward function weights
    reward_weights: Dict[str, float] = field(default_factory=lambda: {
        "resource_utilization": float(os.getenv("REWARD_RESOURCE_UTIL", "0.3")),
        "load_balance": float(os.getenv("REWARD_LOAD_BALANCE", "0.25")),
        "latency": float(os.getenv("REWARD_LATENCY", "0.25")),
        "affinity": float(os.getenv("REWARD_AFFINITY", "0.1")),
        "energy": float(os.getenv("REWARD_ENERGY", "0.1"))
    })

    # API settings
    api_port: int = int(os.getenv("API_PORT", "8000"))
    metrics_port: int = int(os.getenv("METRICS_PORT", "9090"))

    # Kubernetes settings
    kubeconfig_path: str = os.getenv("KUBECONFIG", "")
    in_cluster: bool = os.getenv("IN_CLUSTER", "true").lower() == "true"

    # Metrics collection
    metrics_window: int = int(os.getenv("METRICS_WINDOW", "300"))  # 5 minutes
    metrics_interval: int = int(os.getenv("METRICS_INTERVAL", "10"))  # 10 seconds

    # Performance thresholds
    cpu_threshold: float = float(os.getenv("CPU_THRESHOLD", "0.8"))
    memory_threshold: float = float(os.getenv("MEMORY_THRESHOLD", "0.8"))
    latency_threshold_ms: float = float(os.getenv("LATENCY_THRESHOLD_MS", "100"))

    # Scheduling constraints
    enable_affinity: bool = os.getenv("ENABLE_AFFINITY", "true").lower() == "true"
    enable_anti_affinity: bool = os.getenv("ENABLE_ANTI_AFFINITY", "true").lower() == "true"
    enable_taints: bool = os.getenv("ENABLE_TAINTS", "true").lower() == "true"

    # Exploration settings
    epsilon_start: float = float(os.getenv("EPSILON_START", "1.0"))
    epsilon_end: float = float(os.getenv("EPSILON_END", "0.01"))
    epsilon_decay: float = float(os.getenv("EPSILON_DECAY", "0.995"))

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    enable_tensorboard: bool = os.getenv("ENABLE_TENSORBOARD", "true").lower() == "true"
    tensorboard_dir: str = os.getenv("TENSORBOARD_DIR", "/app/logs/tensorboard")

    def __post_init__(self):
        """Validate configuration"""
        assert sum(self.reward_weights.values()) <= 1.1, "Reward weights should sum to ~1.0"
        assert 0 < self.gamma <= 1.0, "Gamma must be between 0 and 1"
        assert self.learning_rate > 0, "Learning rate must be positive"
