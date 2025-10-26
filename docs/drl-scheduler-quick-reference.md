# DRL Scheduler Quick Reference

## Quick Commands

### Deployment
```bash
# Deploy scheduler
cd src/drl-scheduler
./deploy.sh --project-id ${PROJECT_ID}

# Check status
kubectl get pods -n drl-scheduler-system
kubectl logs -n drl-scheduler-system -l app=drl-scheduler -f
```

### Configuration
```bash
# Update a service to use DRL scheduler
kubectl patch deployment frontend \
  -p '{"spec":{"template":{"spec":{"schedulerName":"drl-scheduler"}}}}'

# Update reward weights
kubectl set env deployment/drl-scheduler -n drl-scheduler-system \
  REWARD_LOAD_BALANCE=0.35 \
  REWARD_LATENCY=0.30
```

### Monitoring
```bash
# Port forward to API
kubectl port-forward -n drl-scheduler-system svc/drl-scheduler 8000:8000

# Get status
curl http://localhost:8000/status | jq

# Get cluster state
curl http://localhost:8000/cluster/state | jq

# Prometheus metrics
curl http://localhost:8000/metrics
```

### Management
```bash
# Trigger training
curl -X POST http://localhost:8000/training/trigger \
  -H "Content-Type: application/json" \
  -d '{"episodes": 10, "save_model": true}'

# Save model
curl -X POST http://localhost:8000/model/save

# Load model
curl -X POST http://localhost:8000/model/load
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/readiness` | Readiness check |
| GET | `/status` | Scheduler status |
| GET | `/config` | Current configuration |
| GET | `/cluster/state` | Cluster state |
| GET | `/cluster/nodes` | All node metrics |
| GET | `/cluster/nodes/{name}` | Specific node metrics |
| POST | `/training/trigger` | Manual training |
| POST | `/model/save` | Save model |
| POST | `/model/load` | Load model |
| GET | `/metrics` | Prometheus metrics |

## Environment Variables

### Core Settings
| Variable | Default | Description |
|----------|---------|-------------|
| `NAMESPACE` | `default` | Namespace to watch |
| `IN_CLUSTER` | `true` | Running in cluster |
| `ENABLE_TRAINING` | `true` | Enable online learning |
| `TRAINING_INTERVAL` | `100` | Train after N schedules |

### Learning Parameters
| Variable | Default | Description |
|----------|---------|-------------|
| `LEARNING_RATE` | `0.0003` | Learning rate |
| `GAMMA` | `0.99` | Discount factor |
| `BATCH_SIZE` | `64` | Training batch size |
| `EPSILON_START` | `1.0` | Initial exploration |
| `EPSILON_END` | `0.01` | Min exploration |
| `EPSILON_DECAY` | `0.995` | Decay rate |

### Reward Weights
| Variable | Default | Description |
|----------|---------|-------------|
| `REWARD_RESOURCE_UTIL` | `0.3` | Resource efficiency |
| `REWARD_LOAD_BALANCE` | `0.25` | Load distribution |
| `REWARD_LATENCY` | `0.25` | Latency optimization |
| `REWARD_AFFINITY` | `0.1` | Affinity compliance |
| `REWARD_ENERGY` | `0.1` | Energy efficiency |

## Workload Profiles

### High Traffic (Frontend)
```yaml
REWARD_LOAD_BALANCE: 0.35
REWARD_LATENCY: 0.30
REWARD_RESOURCE_UTIL: 0.25
```

### Communication Heavy (Backend)
```yaml
REWARD_LATENCY: 0.35
REWARD_AFFINITY: 0.20
REWARD_LOAD_BALANCE: 0.25
```

### Resource Constrained
```yaml
REWARD_RESOURCE_UTIL: 0.40
REWARD_LOAD_BALANCE: 0.30
REWARD_ENERGY: 0.20
```

### Cost Optimized
```yaml
REWARD_ENERGY: 0.35
REWARD_RESOURCE_UTIL: 0.35
REWARD_LOAD_BALANCE: 0.20
```

## Prometheus Metrics

### Scheduling Metrics
- `drl_scheduler_schedule_attempts_total{status="success|failed"}`
- `drl_scheduler_schedule_duration_seconds`
- `drl_scheduler_schedule_reward`

### Training Metrics
- `drl_scheduler_training_episodes_total`
- `drl_scheduler_training_loss`
- `drl_scheduler_exploration_rate`
- `drl_scheduler_experience_buffer_size`

### Cluster Metrics
- `drl_scheduler_cluster_cpu_usage`
- `drl_scheduler_cluster_memory_usage`
- `drl_scheduler_node_count{state="ready|not_ready"}`
- `drl_scheduler_pod_count`

## Troubleshooting

### Pods Not Scheduled
```bash
# Check scheduler logs
kubectl logs -n drl-scheduler-system -l app=drl-scheduler | grep ERROR

# Check pod events
kubectl describe pod <pod-name> | tail -20

# Verify scheduler is running
kubectl get pods -n drl-scheduler-system
```

### Low Performance
```bash
# Increase training frequency
kubectl set env deployment/drl-scheduler -n drl-scheduler-system \
  TRAINING_INTERVAL=50

# Reduce exploration
kubectl set env deployment/drl-scheduler -n drl-scheduler-system \
  EPSILON_START=0.1 EPSILON_END=0.01
```

### High Resource Usage
```bash
# Check scheduler resource usage
kubectl top pod -n drl-scheduler-system

# Increase limits if needed
kubectl set resources deployment/drl-scheduler -n drl-scheduler-system \
  --limits=cpu=2000m,memory=4Gi
```

## Integration Examples

### Single Service
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-service
spec:
  template:
    spec:
      schedulerName: drl-scheduler  # Add this line
      containers:
        - name: app
          image: my-app:latest
```

### With Affinity
```yaml
spec:
  template:
    spec:
      schedulerName: drl-scheduler
      affinity:
        podAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchLabels:
                  app: related-service
              topologyKey: kubernetes.io/hostname
```

### With Resource Constraints
```yaml
spec:
  template:
    spec:
      schedulerName: drl-scheduler
      containers:
        - name: app
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
```

## Python API Usage

```python
import requests

# Get status
response = requests.get("http://localhost:8000/status")
status = response.json()
print(f"Scheduled pods: {status['scheduled_pods']}")

# Trigger training
response = requests.post(
    "http://localhost:8000/training/trigger",
    json={"episodes": 10, "save_model": True}
)
print(response.json())

# Get cluster state
response = requests.get("http://localhost:8000/cluster/state")
cluster = response.json()
print(f"CPU usage: {cluster['cluster_cpu_usage']:.2%}")
```

## File Structure

```
drl-scheduler/
├── main.py                    # Entry point
├── requirements.txt           # Dependencies
├── Dockerfile                 # Container image
├── deploy.sh                  # Deployment script
├── README.md                  # Full documentation
├── scheduler/
│   ├── config.py             # Configuration
│   ├── k8s_scheduler.py      # Main scheduler
│   ├── drl_agent.py          # RL agent
│   ├── models.py             # Neural networks
│   ├── state_observer.py     # Metrics collection
│   └── reward_calculator.py  # Reward function
├── api/
│   └── server.py             # FastAPI server
├── monitoring/
│   └── metrics.py            # Prometheus metrics
└── examples/
    └── usage_example.py      # Usage examples
```

## Resources

- **Documentation**: `src/drl-scheduler/README.md`
- **Integration Guide**: `docs/drl-scheduler-integration.md`
- **Implementation Summary**: `docs/DRL-SCHEDULER-IMPLEMENTATION.md`
- **Example Script**: `src/drl-scheduler/examples/usage_example.py`

## Support

For issues and questions:
- Check logs: `kubectl logs -n drl-scheduler-system -l app=drl-scheduler`
- API status: `curl http://localhost:8000/status`
- Metrics: `curl http://localhost:8000/metrics`
- GitHub: https://github.com/GoogleCloudPlatform/microservices-demo
