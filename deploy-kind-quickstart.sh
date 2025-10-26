#!/bin/bash
# Quick Start Deployment Script for Online Boutique with DRL Scheduler on Kind
# This script automates the deployment process outlined in DEPLOYMENT-INSTRUCTIONS.md

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Check prerequisites
print_header "Step 1: Checking Prerequisites"

if ! command -v kind &> /dev/null; then
    print_error "kind is not installed. Please install it first:"
    echo "  brew install kind"
    exit 1
fi
print_success "kind is installed ($(kind --version))"

if ! command -v kubectl &> /dev/null; then
    print_error "kubectl is not installed. Please install it first:"
    echo "  brew install kubectl"
    exit 1
fi
print_success "kubectl is installed"

if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker Desktop first"
    exit 1
fi
print_success "Docker is installed"

# Check if Docker is running
if ! docker info &> /dev/null; then
    print_error "Docker is not running. Please start Docker Desktop"
    exit 1
fi
print_success "Docker is running"

# Step 2: Create Kind cluster
print_header "Step 2: Creating Kind Cluster"

if kind get clusters | grep -q "online-boutique"; then
    print_warning "Kind cluster 'online-boutique' already exists"
    read -p "Do you want to delete and recreate it? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_warning "Deleting existing cluster..."
        kind delete cluster --name online-boutique
        print_success "Cluster deleted"
    else
        print_warning "Using existing cluster"
    fi
fi

if ! kind get clusters | grep -q "online-boutique"; then
    echo "Creating Kind cluster 'online-boutique'..."
    kind create cluster --name online-boutique
    print_success "Kind cluster created"
else
    print_success "Using existing Kind cluster"
fi

# Verify cluster
kubectl cluster-info --context kind-online-boutique > /dev/null 2>&1
print_success "Cluster is accessible"

# Step 3: Deploy Online Boutique
print_header "Step 3: Deploying Online Boutique Microservices"

echo "Applying kubernetes manifests..."
kubectl apply -f ./release/kubernetes-manifests.yaml

print_success "Microservices deployed"
echo "Waiting for pods to be ready (this may take 2-5 minutes)..."

# Wait for all pods to be ready
kubectl wait --for=condition=ready pod --all --timeout=300s || {
    print_warning "Some pods are still starting. Checking status..."
    kubectl get pods
}

print_success "All microservices are running"

# Step 4: Build and deploy DRL Scheduler
print_header "Step 4: Building DRL Scheduler Docker Image"

echo "Building drl-scheduler:v1.0 image..."
cd src/drl-scheduler
docker build -t drl-scheduler:v1.0 . > /tmp/docker-build.log 2>&1 || {
    print_error "Docker build failed. Check /tmp/docker-build.log for details"
    exit 1
}
cd ../..
print_success "DRL Scheduler image built"

print_header "Step 5: Loading Image into Kind Cluster"

echo "Loading image into Kind..."
kind load docker-image drl-scheduler:v1.0 --name online-boutique
print_success "Image loaded into Kind cluster"

print_header "Step 6: Deploying DRL Scheduler"

# Create namespace
kubectl create namespace drl-scheduler-system 2>/dev/null || {
    print_warning "Namespace drl-scheduler-system already exists"
}

# Deploy scheduler with Kind-compatible config
echo "Deploying DRL scheduler..."
cat kubernetes-manifests/drl-scheduler.yaml | \
  sed 's|gcr.io/PROJECT_ID/drl-scheduler:latest|drl-scheduler:v1.0|g' | \
  sed 's|imagePullPolicy: Always|imagePullPolicy: IfNotPresent|g' | \
  kubectl apply -f -

print_success "DRL Scheduler deployed"

echo "Waiting for DRL scheduler to be ready..."
kubectl wait --for=condition=ready pod -l app=drl-scheduler \
  -n drl-scheduler-system --timeout=180s

print_success "DRL Scheduler is running"

print_header "Step 7: Configuring Services to Use DRL Scheduler"

echo "Patching frontend deployment..."
kubectl patch deployment frontend \
  -p '{"spec":{"template":{"spec":{"schedulerName":"drl-scheduler"}}}}' > /dev/null

echo "Patching recommendationservice deployment..."
kubectl patch deployment recommendationservice \
  -p '{"spec":{"template":{"spec":{"schedulerName":"drl-scheduler"}}}}' > /dev/null

echo "Patching productcatalogservice deployment..."
kubectl patch deployment productcatalogservice \
  -p '{"spec":{"template":{"spec":{"schedulerName":"drl-scheduler"}}}}' > /dev/null

print_success "Services configured to use DRL scheduler"

echo "Waiting for pods to be rescheduled..."
sleep 5
kubectl wait --for=condition=ready pod -l app=frontend --timeout=120s
kubectl wait --for=condition=ready pod -l app=recommendationservice --timeout=120s
kubectl wait --for=condition=ready pod -l app=productcatalogservice --timeout=120s

print_success "Pods rescheduled with DRL scheduler"

print_header "Step 8: Setting Up Port Forwards"

# Kill existing port-forwards
pkill -f "port-forward" 2>/dev/null || true

echo "Starting port-forward for frontend (8080)..."
kubectl port-forward svc/frontend 8080:80 > /tmp/frontend-pf.log 2>&1 &
FRONTEND_PID=$!

echo "Starting port-forward for DRL scheduler API (8001)..."
kubectl port-forward -n drl-scheduler-system svc/drl-scheduler 8001:8000 > /tmp/scheduler-pf.log 2>&1 &
SCHEDULER_PID=$!

sleep 3

# Test endpoints
if curl -s http://localhost:8080 > /dev/null 2>&1; then
    print_success "Frontend is accessible at http://localhost:8080"
else
    print_warning "Frontend port-forward may need a moment to start"
fi

if curl -s http://localhost:8001/health > /dev/null 2>&1; then
    print_success "DRL Scheduler API is accessible at http://localhost:8001"
else
    print_warning "DRL Scheduler API port-forward may need a moment to start"
fi

print_header "Deployment Complete! 🎉"

echo -e "${GREEN}Your Online Boutique with DRL Scheduler is now running!${NC}\n"

echo "📊 Access Points:"
echo "  • Online Boutique: http://localhost:8080"
echo "  • Scheduler API:   http://localhost:8001/status"
echo "  • Health Check:    http://localhost:8001/health"
echo "  • Cluster State:   http://localhost:8001/cluster/state"
echo ""

echo "🔍 Quick Commands:"
echo "  • View all pods:           kubectl get pods --all-namespaces"
echo "  • Check scheduler logs:    kubectl logs -n drl-scheduler-system -l app=drl-scheduler -f"
echo "  • View scheduling events:  kubectl get events --watch | grep -i scheduled"
echo "  • Test scheduler API:      curl http://localhost:8001/status | jq"
echo ""

echo "📋 Pod Status:"
kubectl get pods -o custom-columns=NAME:.metadata.name,READY:.status.containerStatuses[0].ready,STATUS:.status.phase,SCHEDULER:.spec.schedulerName | head -15
echo ""

echo "🎯 DRL Scheduler Status:"
sleep 2
curl -s http://localhost:8001/status 2>/dev/null | jq . || echo "Scheduler API is starting..."
echo ""

echo "📖 For detailed instructions, see DEPLOYMENT-INSTRUCTIONS.md"
echo ""

echo -e "${YELLOW}Note: Port forwards are running in the background.${NC}"
echo -e "${YELLOW}To stop them, run: pkill -f 'port-forward'${NC}"
echo ""

echo "🧹 To cleanup everything:"
echo "  ./cleanup-kind.sh"
echo ""

print_success "Setup complete! Enjoy exploring the DRL scheduler!"
