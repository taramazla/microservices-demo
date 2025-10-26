# DRL-Enhanced Kubernetes Scheduler

A Deep Reinforcement Learning enhanced Kubernetes Scheduler for optimizing microservice placement in the Online Boutique demo application.

## Overview

This scheduler uses Deep Reinforcement Learning (DRL) to learn optimal pod placement policies by considering multiple objectives:

- **Resource Utilization**: Efficient use of CPU and memory across nodes
- **Load Balancing**: Even distribution of workload
- **Latency Optimization**: Co-location of communicating services
- **Affinity/Anti-affinity**: Respecting placement constraints
- **Energy Efficiency**: Workload consolidation for power savings

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              DRL Scheduler System                    │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────────────┐    ┌────────────────┐            │
│  │   K8s API    │◄───┤  State Observer │            │
│  │   Watcher    │    └────────────────┘            │
│  └──────┬───────┘                                   │
│         │                                            │
│         ▼                                            │
│  ┌──────────────┐    ┌────────────────┐            │
│  │  DRL Agent   │◄───┤ Reward         │            │
│  │  (PPO/DQN)   │    │ Calculator     │            │
│  └──────┬───────┘    └────────────────┘            │
│         │                                            │
│         ▼                                            │
│  ┌──────────────┐                                   │
│  │   Scheduler  │                                   │
│  │   Decision   │                                   │
│  └──────┬───────┘                                   │
│         │                                            │
│         ▼                                            │
│  ┌──────────────┐                                   │
│  │  Pod Binding │                                   │
│  └──────────────┘                                   │
│                                                      │
├─────────────────────────────────────────────────────┤
│  API Server (FastAPI) │ Metrics (Prometheus)        │
└─────────────────────────────────────────────────────┘
```

## Features

### 1. Deep Reinforcement Learning
- **Policy Network**: Neural network for action (node) selection
- **Value Network**: State value estimation
- **Experience Replay**: Learning from historical decisions
- **Exploration vs Exploitation**: Epsilon-greedy strategy

### 2. Multi-Objective Reward Function
The scheduler optimizes multiple objectives simultaneously:

```python
Reward = 0.3 × Resource_Utilization +
         0.25 × Load_Balance +
         0.25 × Latency +
         0.1 × Affinity +
         0.1 × Energy_Efficiency
```

### 3. Real-time Monitoring
- Prometheus metrics for scheduling decisions
- TensorBoard for training visualization
- RESTful API for management

### 4. Production Features
- RBAC integration
- Health and readiness checks
- Model persistence
- Graceful shutdown

## Quick Start

### Prerequisites
- Kubernetes cluster (GKE, EKS, or local)
- `kubectl` configured
- Docker for building images

### 1. Build the Scheduler Image

```bash
cd src/drl-scheduler
docker build -t drl-scheduler:v1.0 .
```

For GKE:
```bash
export PROJECT_ID=your-gcp-project-id
docker tag drl-scheduler:v1.0 gcr.io/${PROJECT_ID}/drl-scheduler:v1.0
docker push gcr.io/${PROJECT_ID}/drl-scheduler:v1.0
```

### 2. Deploy the Scheduler

```bash
# Update PROJECT_ID in the manifest
sed -i "s/PROJECT_ID/${PROJECT_ID}/g" kubernetes-manifests/drl-scheduler.yaml

# Deploy
kubectl apply -f kubernetes-manifests/drl-scheduler.yaml
```

### 3. Verify Deployment

```bash
# Check scheduler pod
kubectl get pods -n drl-scheduler-system

# Check logs
kubectl logs -n drl-scheduler-system -l app=drl-scheduler -f

# Check API
kubectl port-forward -n drl-scheduler-system svc/drl-scheduler 8000:8000
curl http://localhost:8000/status
```

### 4. Use the DRL Scheduler for Pods

Add the scheduler name to your pod spec:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: my-pod
spec:
  schedulerName: drl-scheduler
  containers:
    - name: nginx
      image: nginx
```

Or update existing deployments:

```bash
# Example: Update frontend deployment
kubectl patch deployment frontend \
  -p '{"spec":{"template":{"spec":{"schedulerName":"drl-scheduler"}}}}'
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_TRAINING` | `true` | Enable online learning |
| `TRAINING_INTERVAL` | `100` | Train after N scheduling decisions |
| `LEARNING_RATE` | `0.0003` | Learning rate for optimizer |
| `GAMMA` | `0.99` | Discount factor for rewards |
| `EPSILON_START` | `1.0` | Initial exploration rate |
| `EPSILON_END` | `0.01` | Minimum exploration rate |
| `EPSILON_DECAY` | `0.995` | Exploration decay rate |

### Reward Weights

Adjust the multi-objective weights:

```yaml
env:
  - name: REWARD_RESOURCE_UTIL
    value: "0.3"
  - name: REWARD_LOAD_BALANCE
    value: "0.25"
  - name: REWARD_LATENCY
    value: "0.25"
  - name: REWARD_AFFINITY
    value: "0.1"
  - name: REWARD_ENERGY
    value: "0.1"
```

## API Reference

### Status Endpoints

```bash
# Health check
GET /health

# Scheduler status
GET /status

# Cluster state
GET /cluster/state

# Node metrics
GET /cluster/nodes
GET /cluster/nodes/{node_name}
```

### Training Endpoints

```bash
# Trigger training
POST /training/trigger
{
  "episodes": 10,
  "save_model": true
}

# Save model
POST /model/save

# Load model
POST /model/load
```

### Metrics

```bash
# Prometheus metrics
GET /metrics
```

## Monitoring

### Prometheus Metrics

The scheduler exposes the following metrics:

- `drl_scheduler_schedule_attempts_total`: Total scheduling attempts
- `drl_scheduler_schedule_duration_seconds`: Scheduling duration
- `drl_scheduler_schedule_reward`: Reward distribution
- `drl_scheduler_training_episodes_total`: Training episodes
- `drl_scheduler_training_loss`: Current training loss
- `drl_scheduler_exploration_rate`: Current epsilon value
- `drl_scheduler_cluster_cpu_usage`: Cluster CPU usage
- `drl_scheduler_cluster_memory_usage`: Cluster memory usage

### Grafana Dashboard

A sample Grafana dashboard is available in `monitoring/grafana-dashboard.json`.

## Training

### Online Training

The scheduler trains continuously in production:

1. Makes scheduling decision
2. Observes cluster state changes
3. Calculates reward
4. Stores experience
5. Periodically updates model

### Offline Training

For offline training with historical data:

```python
# See examples/offline_training.py
python examples/offline_training.py --data-path /path/to/scheduling-logs
```

## Advanced Usage

### Custom Reward Function

Modify `scheduler/reward_calculator.py` to implement custom reward logic:

```python
async def calculate_reward(self, pod, node, state):
    # Your custom reward logic
    custom_reward = your_calculation()
    return custom_reward
```

### Different RL Algorithms

The framework supports multiple RL algorithms:

- **PPO** (Proximal Policy Optimization) - Default
- **DQN** (Deep Q-Network)
- **A3C** (Asynchronous Advantage Actor-Critic)

Switch algorithm in configuration:

```python
# scheduler/drl_agent.py
from stable_baselines3 import PPO, DQN, A2C
```

## Performance Tuning

### For CPU-Intensive Workloads
```yaml
env:
  - name: REWARD_RESOURCE_UTIL
    value: "0.4"
  - name: REWARD_LOAD_BALANCE
    value: "0.3"
```

### For Latency-Sensitive Applications
```yaml
env:
  - name: REWARD_LATENCY
    value: "0.4"
  - name: REWARD_AFFINITY
    value: "0.2"
```

### For Cost Optimization
```yaml
env:
  - name: REWARD_ENERGY
    value: "0.3"
  - name: REWARD_RESOURCE_UTIL
    value: "0.35"
```

## Troubleshooting

### Scheduler Not Making Decisions

Check logs:
```bash
kubectl logs -n drl-scheduler-system -l app=drl-scheduler
```

Common issues:
- RBAC permissions
- Pod doesn't specify `schedulerName: drl-scheduler`
- No eligible nodes for pod

### Poor Scheduling Performance

1. **Adjust reward weights** based on your workload
2. **Increase training interval** for more stable learning
3. **Reduce exploration rate** after initial training period
4. **Check cluster state observer** for accurate metrics

### Model Not Learning

1. Check training logs in TensorBoard
2. Verify reward function is providing signal
3. Adjust learning rate
4. Increase experience buffer size

## Development

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (with kubeconfig)
export IN_CLUSTER=false
export KUBECONFIG=~/.kube/config
python main.py
```

### Running Tests

```bash
pytest tests/ -v
```

### Code Structure

```
drl-scheduler/
├── main.py                 # Entry point
├── scheduler/
│   ├── config.py          # Configuration
│   ├── k8s_scheduler.py   # Main scheduler logic
│   ├── drl_agent.py       # RL agent
│   ├── models.py          # Neural networks
│   ├── state_observer.py  # Cluster state collection
│   └── reward_calculator.py # Reward function
├── api/
│   └── server.py          # FastAPI server
├── monitoring/
│   └── metrics.py         # Prometheus metrics
└── tests/
    └── ...                # Unit tests
```

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

Copyright 2025 Google LLC

Licensed under the Apache License, Version 2.0

## References

- [Kubernetes Scheduling Framework](https://kubernetes.io/docs/concepts/scheduling-eviction/scheduling-framework/)
- [Deep Reinforcement Learning](https://arxiv.org/abs/1312.5602)
- [Proximal Policy Optimization](https://arxiv.org/abs/1707.06347)
- [Resource Management with Deep RL](https://dl.acm.org/doi/10.1145/3458817.3476142)

## Citation

If you use this scheduler in your research, please cite:

```bibtex
@software{drl_k8s_scheduler,
  title={DRL-Enhanced Kubernetes Scheduler for Microservices},
  author={Google Cloud Platform},
  year={2025},
  url={https://github.com/GoogleCloudPlatform/microservices-demo}
}
```
