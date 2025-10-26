# DRL Scheduler on Kind (Kubernetes in Docker)

This guide explains how to deploy and use the DRL Scheduler on a local kind cluster.

## Prerequisites

```bash
# Install kind
brew install kind  # macOS
# or
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/kind

# Install kubectl (if not already installed)
brew install kubectl

# Install Docker Desktop (required for kind)
# Download from: https://www.docker.com/products/docker-desktop
```

## Step 1: Create Kind Cluster

Create a kind cluster with appropriate configuration:

```bash
# Create kind cluster with specific configuration
cat <<EOF | kind create cluster --name drl-scheduler-demo --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    kubeadmConfigPatches:
    - |
      kind: InitConfiguration
      nodeRegistration:
        kubeletExtraArgs:
          node-labels: "node-role=control-plane"
  - role: worker
    kubeadmConfigPatches:
    - |
      kind: JoinConfiguration
      nodeRegistration:
        kubeletExtraArgs:
          node-labels: "node-role=worker"
  - role: worker
    kubeadmConfigPatches:
    - |
      kind: JoinConfiguration
      nodeRegistration:
        kubeletExtraArgs:
          node-labels: "node-role=worker"
  - role: worker
    kubeadmConfigPatches:
    - |
      kind: JoinConfiguration
      nodeRegistration:
        kubeletExtraArgs:
          node-labels: "node-role=worker"
EOF

# Verify cluster
kubectl cluster-info --context kind-drl-scheduler-demo
kubectl get nodes
```

This creates a cluster with:
- 1 control-plane node
- 3 worker nodes (good for testing scheduling)

## Step 2: Build and Load Scheduler Image

Kind uses local Docker images, so we need to build and load them:

```bash
cd src/drl-scheduler

# Build the image locally
docker build -t drl-scheduler:v1.0 .

# Load image into kind cluster
kind load docker-image drl-scheduler:v1.0 --name drl-scheduler-demo

# Verify image is loaded
docker exec -it drl-scheduler-demo-control-plane crictl images | grep drl-scheduler
```

## Step 3: Deploy DRL Scheduler

Use the kind-specific deployment script:

```bash
# Deploy with kind configuration
./deploy-kind.sh

# Or manually:
kubectl create namespace drl-scheduler-system

# Update manifest for kind (use local image)
cat kubernetes-manifests/drl-scheduler.yaml | \
  sed 's|gcr.io/PROJECT_ID/drl-scheduler:latest|drl-scheduler:v1.0|g' | \
  sed 's|imagePullPolicy: Always|imagePullPolicy: IfNotPresent|g' | \
  kubectl apply -f -
```

## Step 4: Verify Deployment

```bash
# Check scheduler pod
kubectl get pods -n drl-scheduler-system

# View logs
kubectl logs -n drl-scheduler-system -l app=drl-scheduler -f

# Check scheduler is registered
kubectl get pods -n drl-scheduler-system -o yaml | grep schedulerName
```

## Step 5: Deploy Online Boutique

Deploy the microservices demo:

```bash
cd ../..

# Deploy all services
kubectl apply -f release/kubernetes-manifests.yaml

# Wait for pods to be ready
kubectl wait --for=condition=ready pod --all --timeout=300s
```

## Step 6: Configure Services to Use DRL Scheduler

Update specific services to use the DRL scheduler:

```bash
# Update frontend
kubectl patch deployment frontend \
  -p '{"spec":{"template":{"spec":{"schedulerName":"drl-scheduler"}}}}'

# Update recommendation service
kubectl patch deployment recommendationservice \
  -p '{"spec":{"template":{"spec":{"schedulerName":"drl-scheduler"}}}}'

# Update product catalog
kubectl patch deployment productcatalogservice \
  -p '{"spec":{"template":{"spec":{"schedulerName":"drl-scheduler"}}}}'

# Delete pods to trigger rescheduling
kubectl delete pod -l app=frontend
kubectl delete pod -l app=recommendationservice
kubectl delete pod -l app=productcatalogservice
```

## Step 7: Access Services

### Access DRL Scheduler API

```bash
# Port forward scheduler API
kubectl port-forward -n drl-scheduler-system svc/drl-scheduler 8000:8000 &

# Test API
curl http://localhost:8000/health
curl http://localhost:8000/status | jq
curl http://localhost:8000/cluster/state | jq
```

### Access Online Boutique Frontend

```bash
# Port forward frontend
kubectl port-forward deployment/frontend 8080:8080 &

# Open in browser
open http://localhost:8080
```

### Access Prometheus Metrics

```bash
# Port forward metrics
kubectl port-forward -n drl-scheduler-system svc/drl-scheduler 9090:9090 &

# Scrape metrics
curl http://localhost:9090/metrics
```

## Step 8: Monitor Scheduling

### Watch Scheduling Events

```bash
# Watch all events
kubectl get events --watch | grep -i scheduled

# Watch DRL scheduler logs
kubectl logs -n drl-scheduler-system -l app=drl-scheduler -f
```

### Check Pod Distribution

```bash
# See which node each pod is on
kubectl get pods -o wide

# Count pods per node
kubectl get pods -o wide | awk '{print $7}' | sort | uniq -c

# Detailed node view
kubectl get nodes
kubectl describe nodes
```

### Use Example Script

```bash
# Run example monitoring script
cd src/drl-scheduler
python examples/usage_example.py
```

## Kind-Specific Configuration

### Resource Constraints

Kind runs on your local machine, so adjust resource limits:

```yaml
# Update scheduler resources for kind
kubectl patch deployment drl-scheduler -n drl-scheduler-system --type='json' \
  -p='[
    {"op": "replace", "path": "/spec/template/spec/containers/0/resources/requests/cpu", "value": "250m"},
    {"op": "replace", "path": "/spec/template/spec/containers/0/resources/requests/memory", "value": "512Mi"},
    {"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/cpu", "value": "1000m"},
    {"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/memory", "value": "2Gi"}
  ]'
```

### Training Configuration

For kind, use more conservative training settings:

```bash
kubectl set env deployment/drl-scheduler -n drl-scheduler-system \
  TRAINING_INTERVAL=200 \
  BATCH_SIZE=32 \
  ENABLE_TRAINING=true
```

### Storage

Kind uses local storage. The model PVC should work, but you can also use emptyDir for testing:

```yaml
# Use emptyDir instead of PVC (optional)
volumes:
  - name: models
    emptyDir: {}
  - name: logs
    emptyDir: {}
```

## Testing Scenarios

### Test 1: Basic Scheduling

```bash
# Create test deployment
kubectl create deployment test-app --image=nginx --replicas=5
kubectl patch deployment test-app \
  -p '{"spec":{"template":{"spec":{"schedulerName":"drl-scheduler"}}}}'

# Watch scheduling
kubectl get events --watch | grep test-app
```

### Test 2: Load Balancing

```bash
# Create multiple deployments
for i in {1..3}; do
  kubectl create deployment app-${i} --image=nginx --replicas=3
  kubectl patch deployment app-${i} \
    -p '{"spec":{"template":{"spec":{"schedulerName":"drl-scheduler"}}}}'
done

# Check distribution
kubectl get pods -o wide | awk '{print $7}' | sort | uniq -c
```

### Test 3: Affinity Rules

```bash
cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: affinity-test
spec:
  replicas: 3
  selector:
    matchLabels:
      app: affinity-test
  template:
    metadata:
      labels:
        app: affinity-test
    spec:
      schedulerName: drl-scheduler
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchLabels:
                  app: affinity-test
              topologyKey: kubernetes.io/hostname
      containers:
      - name: nginx
        image: nginx
EOF

# Check if pods are spread across nodes
kubectl get pods -l app=affinity-test -o wide
```

## Troubleshooting Kind

### Issue: Image Not Found

```bash
# Rebuild and reload image
cd src/drl-scheduler
docker build -t drl-scheduler:v1.0 .
kind load docker-image drl-scheduler:v1.0 --name drl-scheduler-demo

# Verify
docker exec -it drl-scheduler-demo-control-plane crictl images | grep drl
```

### Issue: Pods Not Scheduling

```bash
# Check scheduler logs
kubectl logs -n drl-scheduler-system -l app=drl-scheduler | tail -50

# Check pod events
kubectl describe pod <pod-name>

# Check scheduler is running
kubectl get pods -n drl-scheduler-system
```

### Issue: Connection Refused (API)

```bash
# Kill existing port-forward
pkill -f "port-forward.*drl-scheduler"

# Restart port-forward
kubectl port-forward -n drl-scheduler-system svc/drl-scheduler 8000:8000
```

### Issue: Out of Resources

```bash
# Check Docker resources
docker stats

# Increase Docker Desktop resources:
# Docker Desktop → Preferences → Resources
# Recommended: 8GB RAM, 4 CPUs

# Scale down services
kubectl scale deployment frontend --replicas=1
kubectl scale deployment recommendationservice --replicas=1
```

## Performance Tips for Kind

### 1. Optimize Docker Resources

```bash
# Docker Desktop → Preferences → Resources
# Set:
# - CPUs: 4-6
# - Memory: 8-12 GB
# - Swap: 2 GB
# - Disk: 60 GB
```

### 2. Use Fewer Replicas

```bash
# Scale down Online Boutique services
kubectl scale deployment --all --replicas=1

# Or use minimal deployment
kubectl apply -f kustomize/components/minimal/
```

### 3. Disable Features

```bash
# Disable training for faster performance
kubectl set env deployment/drl-scheduler -n drl-scheduler-system \
  ENABLE_TRAINING=false

# Reduce metrics collection frequency
kubectl set env deployment/drl-scheduler -n drl-scheduler-system \
  METRICS_INTERVAL=30
```

## Cleanup

### Remove DRL Scheduler

```bash
kubectl delete namespace drl-scheduler-system
```

### Remove Online Boutique

```bash
kubectl delete -f release/kubernetes-manifests.yaml
```

### Delete Kind Cluster

```bash
kind delete cluster --name drl-scheduler-demo
```

## Complete Example Script

Here's a complete script to set up everything:

```bash
#!/bin/bash
# setup-kind-drl-scheduler.sh

set -e

echo "Creating kind cluster..."
cat <<EOF | kind create cluster --name drl-scheduler-demo --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
  - role: worker
  - role: worker
  - role: worker
EOF

echo "Building scheduler image..."
cd src/drl-scheduler
docker build -t drl-scheduler:v1.0 .

echo "Loading image into kind..."
kind load docker-image drl-scheduler:v1.0 --name drl-scheduler-demo

echo "Deploying scheduler..."
kubectl create namespace drl-scheduler-system
cat ../../kubernetes-manifests/drl-scheduler.yaml | \
  sed 's|gcr.io/PROJECT_ID/drl-scheduler:latest|drl-scheduler:v1.0|g' | \
  sed 's|imagePullPolicy: Always|imagePullPolicy: IfNotPresent|g' | \
  kubectl apply -f -

echo "Waiting for scheduler to be ready..."
kubectl wait --for=condition=ready pod -l app=drl-scheduler \
  -n drl-scheduler-system --timeout=300s

echo "Deploying Online Boutique..."
cd ../..
kubectl apply -f release/kubernetes-manifests.yaml

echo "Done! Access services with:"
echo "  kubectl port-forward -n drl-scheduler-system svc/drl-scheduler 8000:8000"
echo "  kubectl port-forward deployment/frontend 8080:8080"
```

## Next Steps

1. **Experiment with scheduling** - Try different pod configurations
2. **Monitor metrics** - Watch how the DRL agent learns
3. **Tune parameters** - Adjust reward weights for your workload
4. **Compare performance** - Test against default scheduler
5. **Scale up** - Add more nodes and pods to test at scale

## Resources

- Kind Documentation: https://kind.sigs.k8s.io/
- DRL Scheduler README: `src/drl-scheduler/README.md`
- Integration Guide: `docs/drl-scheduler-integration.md`
- Quick Reference: `docs/drl-scheduler-quick-reference.md`
