# Quick Start Guide

This directory contains everything you need to deploy the Online Boutique microservices demo with the DRL (Deep Reinforcement Learning) Scheduler on a local Kind cluster.

## 📁 Files Overview

| File | Description |
|------|-------------|
| `DEPLOYMENT-INSTRUCTIONS.md` | **Detailed step-by-step deployment guide** with troubleshooting |
| `deploy-kind-quickstart.sh` | **Automated deployment script** - one command deployment |
| `cleanup-kind.sh` | **Cleanup script** - removes all resources |

## 🚀 Quick Start (Automated)

### Prerequisites
- Docker Desktop (running)
- kind
- kubectl

### One-Command Deployment

```bash
./deploy-kind-quickstart.sh
```

This script will automatically:
1. ✅ Check prerequisites
2. ✅ Create Kind cluster
3. ✅ Deploy Online Boutique (11 microservices)
4. ✅ Build and deploy DRL Scheduler
5. ✅ Configure services to use DRL Scheduler
6. ✅ Set up port forwards
7. ✅ Verify everything is running

**Deployment time:** ~5-10 minutes

### Access Your Applications

After successful deployment:

- **Online Boutique (Frontend):** http://localhost:8080
- **DRL Scheduler API:** http://localhost:8001/status
- **Health Check:** http://localhost:8001/health
- **Cluster State:** http://localhost:8001/cluster/state
- **Metrics:** http://localhost:8001/metrics

## 📖 Manual Deployment

If you prefer to deploy step-by-step or encounter issues with the automated script, follow the detailed guide:

```bash
# Open the detailed instructions
cat DEPLOYMENT-INSTRUCTIONS.md
# or
open DEPLOYMENT-INSTRUCTIONS.md
```

The manual guide includes:
- Detailed explanation of each step
- Expected outputs
- Troubleshooting sections
- Monitoring commands
- Testing procedures

## 🧹 Cleanup

When you're done, clean up all resources:

```bash
./cleanup-kind.sh
```

This will remove:
- Port forwards
- Online Boutique deployments
- DRL Scheduler
- Kind cluster
- (Optional) Docker images and log files

## 📊 Verify Deployment

### Check All Pods
```bash
kubectl get pods --all-namespaces
```

### Check DRL Scheduler
```bash
kubectl get pods -n drl-scheduler-system
kubectl logs -n drl-scheduler-system -l app=drl-scheduler
```

### Check Which Services Use DRL Scheduler
```bash
kubectl get pods -o custom-columns=NAME:.metadata.name,SCHEDULER:.spec.schedulerName
```

### Test API Endpoints
```bash
# Health
curl http://localhost:8001/health

# Status
curl http://localhost:8001/status | jq

# Cluster state
curl http://localhost:8001/cluster/state | jq
```

## 🔍 Monitoring

### Real-time Scheduler Logs
```bash
kubectl logs -n drl-scheduler-system -l app=drl-scheduler -f
```

### Watch Scheduling Events
```bash
kubectl get events --watch | grep -i scheduled
```

### Monitor Cluster State
```bash
watch -n 2 'curl -s http://localhost:8001/status | jq'
```

### View Scheduling Rewards
```bash
kubectl logs -n drl-scheduler-system -l app=drl-scheduler | grep reward
```

## 🐛 Troubleshooting

### Port Forwards Not Working

```bash
# Kill existing port-forwards
pkill -f "port-forward"

# Restart them
kubectl port-forward svc/frontend 8080:80 &
kubectl port-forward -n drl-scheduler-system svc/drl-scheduler 8001:8000 &
```

### Pods Not Starting

```bash
# Check pod status
kubectl get pods

# Describe problematic pod
kubectl describe pod <pod-name>

# Check logs
kubectl logs <pod-name>
```

### DRL Scheduler Not Scheduling

```bash
# Check scheduler status
kubectl get pods -n drl-scheduler-system

# View scheduler logs
kubectl logs -n drl-scheduler-system -l app=drl-scheduler

# Verify RBAC
kubectl get clusterrole drl-scheduler
kubectl get clusterrolebinding drl-scheduler
```

For more troubleshooting, see the **Troubleshooting** section in `DEPLOYMENT-INSTRUCTIONS.md`.

## 📚 Architecture

### Microservices (11 services)
- **Frontend** - Web UI (uses DRL Scheduler ✓)
- **Cart Service** - Shopping cart
- **Product Catalog Service** - Product listings (uses DRL Scheduler ✓)
- **Currency Service** - Currency conversion
- **Payment Service** - Payment processing
- **Shipping Service** - Shipping calculations
- **Email Service** - Email notifications
- **Checkout Service** - Order processing
- **Recommendation Service** - Product recommendations (uses DRL Scheduler ✓)
- **Ad Service** - Advertisement serving
- **Load Generator** - Synthetic traffic

### DRL Scheduler
- **AI-powered Kubernetes scheduler**
- Uses Deep Reinforcement Learning for intelligent pod placement
- Optimizes for:
  - Resource utilization
  - Load balancing
  - Latency
  - Pod affinity
  - Energy efficiency

## 🎯 What's Being Demonstrated

1. **Microservices Architecture** - 11 services in different languages
2. **Kubernetes Scheduling** - Custom scheduler implementation
3. **Deep Reinforcement Learning** - AI-driven decision making
4. **Service Mesh** - Inter-service communication
5. **Observability** - Metrics, logs, and monitoring
6. **API Design** - RESTful API for scheduler

## 📈 Performance Metrics

The DRL Scheduler provides:
- **Schedule Success Rate** - Percentage of successful placements
- **Average Reward** - Quality of scheduling decisions (~0.79 is good)
- **Schedule Duration** - Time to make scheduling decisions
- **Cluster Utilization** - CPU and memory usage
- **Load Balance Score** - Distribution across nodes

## 🎓 Learning Resources

- [DRL Scheduler on Kind Guide](docs/drl-scheduler-kind.md)
- [DRL Scheduler Integration](docs/drl-scheduler-integration.md)
- [DRL Scheduler Quick Reference](docs/drl-scheduler-quick-reference.md)
- [Development Guide](docs/development-guide.md)
- [Kind Documentation](https://kind.sigs.k8s.io/)
- [Kubernetes Scheduling](https://kubernetes.io/docs/concepts/scheduling-eviction/)

## 🆘 Getting Help

If you encounter issues:

1. Check the **Troubleshooting** section in `DEPLOYMENT-INSTRUCTIONS.md`
2. Review logs: `kubectl logs <pod-name>`
3. Check events: `kubectl get events --sort-by='.lastTimestamp'`
4. Verify resources: `kubectl describe pod <pod-name>`

## 🤝 Contributing

To contribute improvements to this deployment:

1. Test your changes with the automated script
2. Update `DEPLOYMENT-INSTRUCTIONS.md` if needed
3. Ensure cleanup script works correctly
4. Document any new features or requirements

## 📝 Notes

- **Deployment target:** Local Kind cluster (single node)
- **Resource requirements:** ~8GB RAM, 4 CPUs recommended
- **Deployment time:** 5-10 minutes
- **Internet required:** For pulling container images
- **OS:** Tested on macOS (should work on Linux)

## ✅ Success Criteria

Your deployment is successful when:

1. ✅ All 12 pods are `Running` and `Ready`
2. ✅ DRL scheduler pod is running in `drl-scheduler-system` namespace
3. ✅ Frontend accessible at http://localhost:8080
4. ✅ Scheduler API responds at http://localhost:8001/health
5. ✅ Scheduler logs show successful scheduling with rewards ~0.78-0.79
6. ✅ Three services (frontend, recommendationservice, productcatalogservice) use `drl-scheduler`

## 🎉 Next Steps

After successful deployment:

1. **Explore the store** - Browse products, add to cart, checkout
2. **Monitor scheduling** - Watch DRL scheduler make decisions
3. **Scale services** - Test scheduler with different loads
4. **Compare performance** - Observe DRL vs default scheduler
5. **Experiment** - Try different configurations

---

**Happy deploying! 🚀**

For questions or issues, refer to `DEPLOYMENT-INSTRUCTIONS.md` or the troubleshooting sections.
