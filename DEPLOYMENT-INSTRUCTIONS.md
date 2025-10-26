# Online Boutique with DRL Scheduler - Deployment Instructions

This guide provides step-by-step instructions to deploy the Online Boutique microservices demo with the DRL (Deep Reinforcement Learning) Scheduler on a local Kind (Kubernetes in Docker) cluster.

## Prerequisites

Before starting, ensure you have the following installed:

- **Docker Desktop** (required for Kind)
- **kubectl** - Kubernetes command-line tool
- **kind** - Kubernetes in Docker
- **curl** and **jq** (optional, for testing API endpoints)

### Installation Commands (macOS)

```bash
# Install Kind
brew install kind

# Install kubectl (if not already installed)
brew install kubectl

# Verify installations
kind --version
kubectl version --client
docker --version
```

## Step 1: Clone the Repository

```bash
git clone --depth 1 --branch v0 https://github.com/GoogleCloudPlatform/microservices-demo.git
cd microservices-demo/
```

## Step 2: Create Kind Cluster

Create a local Kubernetes cluster using Kind:

```bash
kind create cluster --name online-boutique
```

**Expected Output:**
```
Creating cluster "online-boutique" ...
 ✓ Ensuring node image (kindest/node:v1.34.0) 🖼
 ✓ Preparing nodes 📦
 ✓ Writing configuration 📜
 ✓ Starting control-plane 🕹️
 ✓ Installing CNI 🔌
 ✓ Installing StorageClass 💾
Set kubectl context to "kind-online-boutique"
```

**Verify the cluster:**
```bash
kubectl cluster-info --context kind-online-boutique
kubectl get nodes
```

You should see one node in `Ready` status.

## Step 3: Deploy Online Boutique Microservices

Deploy all microservices to the cluster:

```bash
kubectl apply -f ./release/kubernetes-manifests.yaml
```

**Expected Output:**
```
deployment.apps/emailservice created
service/emailservice created
serviceaccount/emailservice created
deployment.apps/checkoutservice created
...
(11 microservices will be created)
```

**Monitor pod deployment:**
```bash
kubectl get pods
```

Wait for all pods to show `1/1 READY` and `Running` status. This may take 2-5 minutes as container images are pulled.

**Expected Output:**
```
NAME                                     READY   STATUS    RESTARTS   AGE
adservice-xxx                            1/1     Running   0          2m
cartservice-xxx                          1/1     Running   0          2m
checkoutservice-xxx                      1/1     Running   0          2m
currencyservice-xxx                      1/1     Running   0          2m
emailservice-xxx                         1/1     Running   0          2m
frontend-xxx                             1/1     Running   0          2m
loadgenerator-xxx                        1/1     Running   0          2m
paymentservice-xxx                       1/1     Running   0          2m
productcatalogservice-xxx                1/1     Running   0          2m
recommendationservice-xxx                1/1     Running   0          2m
redis-cart-xxx                           1/1     Running   0          2m
shippingservice-xxx                      1/1     Running   0          2m
```

## Step 4: Build and Deploy DRL Scheduler

### 4.1 Build the DRL Scheduler Docker Image

Navigate to the DRL scheduler directory and build the image:

```bash
cd src/drl-scheduler
docker build -t drl-scheduler:v1.0 .
cd ../..
```

**Expected Output:**
```
[+] Building 90.1s (13/13) FINISHED
...
=> exporting to image
=> => naming to docker.io/library/drl-scheduler:v1.0
```

### 4.2 Load Image into Kind Cluster

Load the locally built image into the Kind cluster:

```bash
kind load docker-image drl-scheduler:v1.0 --name online-boutique
```

**Expected Output:**
```
Image: "drl-scheduler:v1.0" with ID "sha256:..." not yet present on node
"online-boutique-control-plane", loading...
```

### 4.3 Create DRL Scheduler Namespace

```bash
kubectl create namespace drl-scheduler-system
```

### 4.4 Deploy DRL Scheduler

Deploy the scheduler with Kind-compatible configuration:

```bash
cat kubernetes-manifests/drl-scheduler.yaml | \
  sed 's|gcr.io/PROJECT_ID/drl-scheduler:latest|drl-scheduler:v1.0|g' | \
  sed 's|imagePullPolicy: Always|imagePullPolicy: IfNotPresent|g' | \
  kubectl apply -f -
```

**Expected Output:**
```
namespace/drl-scheduler-system configured
serviceaccount/drl-scheduler created
clusterrole.rbac.authorization.k8s.io/drl-scheduler created
clusterrolebinding.rbac.authorization.k8s.io/drl-scheduler created
configmap/drl-scheduler-config created
persistentvolumeclaim/drl-scheduler-models created
deployment.apps/drl-scheduler created
service/drl-scheduler created
service/drl-scheduler-metrics created
```

### 4.5 Verify DRL Scheduler Deployment

```bash
kubectl get pods -n drl-scheduler-system
```

Wait for the scheduler pod to be `Running`:

```bash
kubectl wait --for=condition=ready pod -l app=drl-scheduler \
  -n drl-scheduler-system --timeout=180s
```

**Check scheduler logs:**
```bash
kubectl logs -n drl-scheduler-system -l app=drl-scheduler --tail=20
```

You should see initialization logs like:
```
INFO - DRL Scheduler initialization complete
INFO - API server starting on port 8000
INFO - Starting scheduling loop...
```

## Step 5: Configure Services to Use DRL Scheduler

Patch specific services to use the DRL scheduler:

### 5.1 Frontend Service

```bash
kubectl patch deployment frontend \
  -p '{"spec":{"template":{"spec":{"schedulerName":"drl-scheduler"}}}}'
```

### 5.2 Recommendation Service

```bash
kubectl patch deployment recommendationservice \
  -p '{"spec":{"template":{"spec":{"schedulerName":"drl-scheduler"}}}}'
```

### 5.3 Product Catalog Service

```bash
kubectl patch deployment productcatalogservice \
  -p '{"spec":{"template":{"spec":{"schedulerName":"drl-scheduler"}}}}'
```

**Expected Output for each:**
```
deployment.apps/frontend patched
deployment.apps/recommendationservice patched
deployment.apps/productcatalogservice patched
```

### 5.4 Verify Pods Are Rescheduled

The pods will automatically restart with the new scheduler:

```bash
kubectl get pods
```

Check which scheduler is being used:

```bash
kubectl get pods -o custom-columns=NAME:.metadata.name,SCHEDULER:.spec.schedulerName
```

**Expected Output:**
```
NAME                                     SCHEDULER
frontend-xxx                             drl-scheduler
recommendationservice-xxx                drl-scheduler
productcatalogservice-xxx                drl-scheduler
(other services will show default-scheduler or <none>)
```

### 5.5 Check DRL Scheduler Activity

View scheduling events in the logs:

```bash
kubectl logs -n drl-scheduler-system -l app=drl-scheduler | grep "Successfully scheduled"
```

**Expected Output:**
```
INFO - Successfully scheduled frontend-xxx to online-boutique-control-plane (reward: 0.789, duration: 0.037s)
INFO - Successfully scheduled recommendationservice-xxx to online-boutique-control-plane (reward: 0.790, duration: 0.015s)
INFO - Successfully scheduled productcatalogservice-xxx to online-boutique-control-plane (reward: 0.789, duration: 0.020s)
```

## Step 6: Access the Applications

### 6.1 Access Online Boutique Frontend

Set up port forwarding to access the web application:

```bash
kubectl port-forward svc/frontend 8080:80 > /tmp/frontend-pf.log 2>&1 &
```

**Open in browser:**
- URL: http://localhost:8080
- You should see the Online Boutique e-commerce store

**Test with curl:**
```bash
curl -s -I http://localhost:8080 | head -3
```

**Expected Output:**
```
HTTP/1.1 200 OK
Set-Cookie: shop_session-id=...
Date: ...
```

### 6.2 Access DRL Scheduler API

Set up port forwarding for the scheduler API:

```bash
kubectl port-forward -n drl-scheduler-system svc/drl-scheduler 8001:8000 > /tmp/scheduler-pf.log 2>&1 &
```

**Test API endpoints:**

#### Health Check
```bash
curl http://localhost:8001/health
```

**Expected Output:**
```json
{"status":"healthy"}
```

#### Scheduler Status
```bash
curl http://localhost:8001/status | jq
```

**Expected Output:**
```json
{
  "status": "running",
  "scheduled_pods": 6,
  "failed_schedules": 0,
  "training_episodes": 0,
  "epsilon": 0.985,
  "model_version": "1.0.0"
}
```

#### Cluster State
```bash
curl http://localhost:8001/cluster/state | jq
```

**Expected Output:**
```json
{
  "cluster_cpu_usage": 0.38,
  "cluster_memory_usage": 0.34,
  "total_nodes": 1,
  "ready_nodes": 1,
  "total_pods": 22,
  "load_balance_score": 1.0,
  "timestamp": "2025-10-26 ..."
}
```

#### Prometheus Metrics
```bash
curl http://localhost:8001/metrics | grep drl_scheduler_schedule_reward
```

## Step 7: Monitoring and Validation

### 7.1 Check All Pods Status

```bash
kubectl get pods --all-namespaces
```

### 7.2 Monitor DRL Scheduler Logs

**Real-time logs:**
```bash
kubectl logs -n drl-scheduler-system -l app=drl-scheduler -f
```

**Recent scheduling decisions:**
```bash
kubectl logs -n drl-scheduler-system -l app=drl-scheduler --tail=50 | grep reward
```

### 7.3 View Scheduling Events

```bash
kubectl get events --watch | grep -i scheduled
```

### 7.4 Check Service Endpoints

```bash
kubectl get services --all-namespaces
```

### 7.5 Test Application Functionality

Visit http://localhost:8080 and verify:
- ✅ Homepage loads with product listings
- ✅ Can view individual products
- ✅ Can add items to cart
- ✅ Can view cart
- ✅ Can proceed to checkout

## Step 8: Optional - Scale Services

Test the DRL scheduler by scaling services:

### Scale Up
```bash
kubectl scale deployment frontend --replicas=3
kubectl scale deployment recommendationservice --replicas=2
```

### Monitor Scheduling
```bash
kubectl get pods -w
kubectl logs -n drl-scheduler-system -l app=drl-scheduler -f
```

### Scale Down
```bash
kubectl scale deployment frontend --replicas=1
kubectl scale deployment recommendationservice --replicas=1
```

## Troubleshooting

### Issue: Pods Not Starting

**Check pod status:**
```bash
kubectl describe pod <pod-name>
```

**Check events:**
```bash
kubectl get events --sort-by='.lastTimestamp'
```

### Issue: DRL Scheduler Not Scheduling

**Check scheduler logs:**
```bash
kubectl logs -n drl-scheduler-system -l app=drl-scheduler
```

**Verify scheduler is running:**
```bash
kubectl get pods -n drl-scheduler-system
```

**Check RBAC permissions:**
```bash
kubectl get clusterrole drl-scheduler -o yaml
kubectl get clusterrolebinding drl-scheduler -o yaml
```

### Issue: Frontend Returns 500 Error

**Check cart service:**
```bash
kubectl get pods -l app=cartservice
kubectl logs -l app=cartservice
```

**Check redis:**
```bash
kubectl get pods -l app=redis-cart
kubectl logs -l app=redis-cart
```

**Restart services:**
```bash
kubectl rollout restart deployment cartservice
kubectl rollout restart deployment frontend
```

### Issue: Port Forward Not Working

**Kill existing port-forwards:**
```bash
pkill -f "port-forward"
```

**Restart port-forwards:**
```bash
kubectl port-forward svc/frontend 8080:80 &
kubectl port-forward -n drl-scheduler-system svc/drl-scheduler 8001:8000 &
```

**Check if ports are in use:**
```bash
lsof -i :8080
lsof -i :8001
```

### Issue: Out of Docker Resources

**Check Docker stats:**
```bash
docker stats
```

**Increase Docker resources:**
- Docker Desktop → Settings → Resources
- Recommended: 8GB RAM, 4 CPUs, 60GB disk

**Scale down services:**
```bash
kubectl scale deployment loadgenerator --replicas=0
```

## Cleanup

### Stop Port Forwards
```bash
pkill -f "port-forward"
```

### Delete Online Boutique
```bash
kubectl delete -f ./release/kubernetes-manifests.yaml
```

### Delete DRL Scheduler
```bash
kubectl delete namespace drl-scheduler-system
```

### Delete Kind Cluster
```bash
kind delete cluster --name online-boutique
```

### Verify Cleanup
```bash
kind get clusters
docker ps
```

## Quick Reference Commands

### Status Checks
```bash
# All pods
kubectl get pods --all-namespaces

# DRL scheduler
kubectl get pods -n drl-scheduler-system

# Services
kubectl get svc

# Nodes
kubectl get nodes
```

### Logs
```bash
# Frontend
kubectl logs -l app=frontend --tail=50

# DRL scheduler
kubectl logs -n drl-scheduler-system -l app=drl-scheduler --tail=50

# All services
kubectl logs -l app=<service-name>
```

### API Testing
```bash
# Frontend
curl http://localhost:8080

# Scheduler health
curl http://localhost:8001/health

# Scheduler status
curl http://localhost:8001/status | jq

# Cluster state
curl http://localhost:8001/cluster/state | jq

# Metrics
curl http://localhost:8001/metrics
```

## Summary

You have successfully deployed:

1. ✅ **Kind Kubernetes Cluster** - Local development cluster
2. ✅ **Online Boutique** - 11 microservices e-commerce application
3. ✅ **DRL Scheduler** - AI-powered Kubernetes scheduler
4. ✅ **Port Forwards** - Access to frontend (8080) and scheduler API (8001)

**Access Points:**
- **Online Boutique:** http://localhost:8080
- **DRL Scheduler API:** http://localhost:8001/status
- **Scheduler Health:** http://localhost:8001/health
- **Cluster State:** http://localhost:8001/cluster/state
- **Metrics:** http://localhost:8001/metrics

## Next Steps

- Explore the DRL scheduler API endpoints
- Scale services and observe intelligent scheduling decisions
- Monitor scheduling metrics and rewards
- Compare DRL scheduler performance with default scheduler
- Experiment with different workload patterns

## Additional Resources

- [Development Guide](docs/development-guide.md)
- [DRL Scheduler on Kind](docs/drl-scheduler-kind.md)
- [DRL Scheduler Integration](docs/drl-scheduler-integration.md)
- [DRL Scheduler Quick Reference](docs/drl-scheduler-quick-reference.md)
- [Kind Documentation](https://kind.sigs.k8s.io/)
- [Kubernetes Documentation](https://kubernetes.io/docs/)

---

**Last Updated:** October 26, 2025
**Version:** 1.0.0
**Cluster:** Kind (Kubernetes in Docker)
