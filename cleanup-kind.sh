#!/bin/bash
# Cleanup Script for Online Boutique with DRL Scheduler on Kind

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

print_header "Cleanup: Online Boutique with DRL Scheduler"

echo "This will remove:"
echo "  • Port forwards"
echo "  • Online Boutique deployments"
echo "  • DRL Scheduler"
echo "  • Kind cluster 'online-boutique'"
echo ""

read -p "Are you sure you want to continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cleanup cancelled"
    exit 0
fi

# Step 1: Stop port forwards
print_header "Step 1: Stopping Port Forwards"

if pgrep -f "port-forward" > /dev/null; then
    echo "Killing port-forward processes..."
    pkill -f "port-forward" || true
    print_success "Port forwards stopped"
else
    print_warning "No port-forward processes found"
fi

# Step 2: Delete Online Boutique
print_header "Step 2: Deleting Online Boutique Deployments"

if kubectl get namespace default &> /dev/null; then
    echo "Deleting Online Boutique services..."
    kubectl delete -f ./release/kubernetes-manifests.yaml --ignore-not-found=true
    print_success "Online Boutique deleted"
else
    print_warning "Cluster not accessible"
fi

# Step 3: Delete DRL Scheduler
print_header "Step 3: Deleting DRL Scheduler"

if kubectl get namespace drl-scheduler-system &> /dev/null; then
    echo "Deleting DRL scheduler namespace..."
    kubectl delete namespace drl-scheduler-system
    print_success "DRL Scheduler deleted"
else
    print_warning "DRL Scheduler namespace not found"
fi

# Step 4: Delete Kind cluster
print_header "Step 4: Deleting Kind Cluster"

if kind get clusters | grep -q "online-boutique"; then
    echo "Deleting Kind cluster 'online-boutique'..."
    kind delete cluster --name online-boutique
    print_success "Kind cluster deleted"
else
    print_warning "Kind cluster 'online-boutique' not found"
fi

# Step 5: Verify cleanup
print_header "Step 5: Verifying Cleanup"

echo "Checking for remaining Kind clusters..."
CLUSTERS=$(kind get clusters 2>/dev/null || echo "")
if [ -z "$CLUSTERS" ]; then
    print_success "No Kind clusters remaining"
else
    print_warning "Other Kind clusters still exist:"
    echo "$CLUSTERS"
fi

echo ""
echo "Checking for running containers..."
CONTAINERS=$(docker ps --filter "name=online-boutique" --format "{{.Names}}" 2>/dev/null || echo "")
if [ -z "$CONTAINERS" ]; then
    print_success "No related containers running"
else
    print_warning "Some containers are still running:"
    echo "$CONTAINERS"
fi

# Step 6: Optional cleanup
print_header "Step 6: Optional Cleanup"

echo ""
read -p "Do you want to remove the Docker image 'drl-scheduler:v1.0'? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if docker images | grep -q "drl-scheduler.*v1.0"; then
        docker rmi drl-scheduler:v1.0 || print_warning "Could not remove image"
        print_success "Docker image removed"
    else
        print_warning "Image not found"
    fi
fi

echo ""
read -p "Do you want to remove log files in /tmp? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -f /tmp/frontend-pf.log /tmp/scheduler-pf.log /tmp/docker-build.log /tmp/pf.log /tmp/drl-pf.log
    print_success "Log files removed"
fi

print_header "Cleanup Complete! ✓"

echo -e "${GREEN}All resources have been cleaned up.${NC}"
echo ""
echo "To redeploy, run:"
echo "  ./deploy-kind-quickstart.sh"
echo ""
echo "Or follow the manual steps in:"
echo "  DEPLOYMENT-INSTRUCTIONS.md"
echo ""

print_success "Cleanup successful!"
