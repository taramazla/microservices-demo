# DRL Scheduler Integration Guide for Online Boutique

This guide shows how to integrate the DRL Scheduler with the Online Boutique microservices demo.

## Prerequisites

1. Kubernetes cluster running
2. Online Boutique deployed
3. DRL Scheduler built and ready

## Step 1: Deploy DRL Scheduler

```bash
cd src/drl-scheduler

# For GKE
export PROJECT_ID=your-gcp-project-id
./deploy.sh --project-id ${PROJECT_ID}

# For local clusters (minikube, kind)
./deploy.sh
```

## Step 2: Configure Microservices to Use DRL Scheduler

You can configure individual services or all services to use the DRL scheduler.

### Option A: Update All Services

Create a kustomization patch:

```bash
cat <<EOF > kustomize/components/drl-scheduler/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1alpha1
kind: Component

patches:
  - target:
      kind: Deployment
    patch: |-
      - op: add
        path: /spec/template/spec/schedulerName
        value: drl-scheduler
EOF
```

Apply with kustomize:

```bash
kubectl apply -k kustomize/components/drl-scheduler
```

### Option B: Update Individual Services

Update specific deployments:

```bash
# Frontend
kubectl patch deployment frontend \
  -p '{"spec":{"template":{"spec":{"schedulerName":"drl-scheduler"}}}}'

# Recommendation Service (stateful, benefits from intelligent placement)
kubectl patch deployment recommendationservice \
  -p '{"spec":{"template":{"spec":{"schedulerName":"drl-scheduler"}}}}'

# Product Catalog Service
kubectl patch deployment productcatalogservice \
  -p '{"spec":{"template":{"spec":{"schedulerName":"drl-scheduler"}}}}'

# Cart Service
kubectl patch deployment cartservice \
  -p '{"spec":{"template":{"spec":{"schedulerName":"drl-scheduler"}}}}'
```

### Option C: Update Manifest Files

Edit the YAML files directly:

```yaml
# kubernetes-manifests/frontend.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
spec:
  template:
    spec:
      schedulerName: drl-scheduler  # Add this line
      containers:
        - name: server
          # ... rest of spec
```

## Step 3: Trigger Pod Rescheduling

Delete pods to trigger rescheduling with DRL scheduler:

```bash
# Delete all pods (will be recreated with DRL scheduler)
kubectl delete pods --all

# Or delete specific service pods
kubectl delete pod -l app=frontend
kubectl delete pod -l app=recommendationservice
kubectl delete pod -l app=productcatalogservice
```

## Step 4: Monitor DRL Scheduler

### Check Scheduler Status

```bash
# Port forward to scheduler API
kubectl port-forward -n drl-scheduler-system svc/drl-scheduler 8000:8000 &

# Check status
curl http://localhost:8000/status

# Get cluster state
curl http://localhost:8000/cluster/state

# Get node metrics
curl http://localhost:8000/cluster/nodes | jq
```

### View Logs

```bash
# Follow scheduler logs
kubectl logs -n drl-scheduler-system -l app=drl-scheduler -f

# View specific events
kubectl get events -n drl-scheduler-system --sort-by='.lastTimestamp'
```

### Prometheus Metrics

```bash
# Port forward to metrics
kubectl port-forward -n drl-scheduler-system svc/drl-scheduler-metrics 9090:9090 &

# Scrape metrics
curl http://localhost:9090/metrics
```

## Step 5: Performance Testing

### Load Generation

The Online Boutique includes a load generator. Ensure it's running:

```bash
kubectl get pod -l app=loadgenerator
```

### Observe Scheduling Decisions

```bash
# Watch scheduling events
kubectl get events --watch | grep -i scheduled

# Check pod distribution
kubectl get pods -o wide | awk '{print $7}' | sort | uniq -c
```

### Compare with Default Scheduler

To compare performance:

1. Record baseline with default scheduler
2. Switch to DRL scheduler
3. Compare metrics:
   - Pod scheduling latency
   - Resource utilization
   - Service latency
   - Cost (node count)

## Step 6: Tuning for Online Boutique

The Online Boutique has specific characteristics that can be optimized:

### For Frontend (high traffic)
```yaml
env:
  - name: REWARD_LOAD_BALANCE
    value: "0.35"  # Increased load balancing
  - name: REWARD_LATENCY
    value: "0.30"  # Focus on latency
```

### For Backend Services (communication-heavy)
```yaml
env:
  - name: REWARD_LATENCY
    value: "0.35"  # Optimize for co-location
  - name: REWARD_AFFINITY
    value: "0.20"  # Respect service affinity
```

### For Resource Optimization
```yaml
env:
  - name: REWARD_RESOURCE_UTIL
    value: "0.35"
  - name: REWARD_ENERGY
    value: "0.20"  # Consolidate workloads
```

## Step 7: Advanced Configuration

### Service-Specific Affinity Rules

Add affinity rules for related services:

```yaml
# frontend.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
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
                matchExpressions:
                - key: app
                  operator: In
                  values:
                  - productcatalogservice
                  - cartservice
                  - recommendationservice
              topologyKey: kubernetes.io/hostname
```

### Resource Quotas

The DRL scheduler respects resource quotas:

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: compute-quota
spec:
  hard:
    requests.cpu: "10"
    requests.memory: 20Gi
    limits.cpu: "20"
    limits.memory: 40Gi
```

## Monitoring Dashboard

### Grafana Setup

1. Deploy Prometheus (if not already):
```bash
kubectl apply -f monitoring/prometheus.yaml
```

2. Deploy Grafana:
```bash
kubectl apply -f monitoring/grafana.yaml
```

3. Import dashboard:
```bash
# Port forward to Grafana
kubectl port-forward -n monitoring svc/grafana 3000:3000

# Open http://localhost:3000
# Import dashboard from monitoring/grafana-dashboard.json
```

### Key Metrics to Monitor

- **drl_scheduler_schedule_reward**: Reward distribution
- **drl_scheduler_cluster_cpu_usage**: Cluster utilization
- **drl_scheduler_schedule_duration_seconds**: Scheduling latency
- **drl_scheduler_training_loss**: Model learning progress

## Troubleshooting

### Pods Stuck in Pending

```bash
# Check scheduler logs
kubectl logs -n drl-scheduler-system -l app=drl-scheduler | grep -i error

# Check pod events
kubectl describe pod <pod-name> | grep -i events

# Common issues:
# 1. No eligible nodes
# 2. Resource constraints
# 3. Affinity rules too strict
```

### Poor Performance

```bash
# Check reward values
curl http://localhost:8000/cluster/state | jq '.load_balance_score'

# Adjust reward weights based on workload
kubectl set env deployment/drl-scheduler \
  -n drl-scheduler-system \
  REWARD_LOAD_BALANCE=0.35
```

### Training Not Improving

```bash
# Increase training frequency
kubectl set env deployment/drl-scheduler \
  -n drl-scheduler-system \
  TRAINING_INTERVAL=50

# Check training logs
kubectl logs -n drl-scheduler-system -l app=drl-scheduler | grep "Training episode"
```

## Rollback

To revert to default scheduler:

```bash
# Remove schedulerName from all deployments
kubectl patch deployment frontend \
  --type json \
  -p='[{"op": "remove", "path": "/spec/template/spec/schedulerName"}]'

# Or reapply original manifests
kubectl apply -f release/kubernetes-manifests.yaml
```

## Next Steps

1. **Experiment with reward weights** for your workload
2. **Enable continuous training** for adaptation
3. **Integrate with autoscaling** for dynamic clusters
4. **Export trained models** for other environments

## Support

For issues and questions:
- Check logs: `kubectl logs -n drl-scheduler-system -l app=drl-scheduler`
- API status: `curl http://localhost:8000/status`
- GitHub Issues: https://github.com/GoogleCloudPlatform/microservices-demo/issues
