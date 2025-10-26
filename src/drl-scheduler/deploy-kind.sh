#!/bin/bash
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

# Deploy DRL Scheduler to Kind (Kubernetes in Docker)

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  DRL Scheduler - Kind Deployment Script               ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"

# Configuration
IMAGE_NAME="drl-scheduler"
IMAGE_TAG=${IMAGE_TAG:-"v1.0"}
CLUSTER_NAME=${CLUSTER_NAME:-"drl-scheduler-demo"}
NUM_WORKERS=${NUM_WORKERS:-3}

# Check prerequisites
echo -e "\n${YELLOW}Checking prerequisites...${NC}"

command -v docker >/dev/null 2>&1 || {
  echo -e "${RED}✗ Docker is required but not installed.${NC}" >&2
  exit 1
}
echo -e "${GREEN}✓ Docker found${NC}"

command -v kubectl >/dev/null 2>&1 || {
  echo -e "${RED}✗ kubectl is required but not installed.${NC}" >&2
  exit 1
}
echo -e "${GREEN}✓ kubectl found${NC}"

command -v kind >/dev/null 2>&1 || {
  echo -e "${RED}✗ kind is required but not installed.${NC}"
  echo -e "${YELLOW}Install with: brew install kind${NC}" >&2
  exit 1
}
echo -e "${GREEN}✓ kind found${NC}"

# Parse arguments
CREATE_CLUSTER=true
BUILD_IMAGE=true
DEPLOY_SCHEDULER=true

while [[ $# -gt 0 ]]; do
  case $1 in
    --skip-cluster)
      CREATE_CLUSTER=false
      shift
      ;;
    --skip-build)
      BUILD_IMAGE=false
      shift
      ;;
    --cluster-name)
      CLUSTER_NAME="$2"
      shift 2
      ;;
    --num-workers)
      NUM_WORKERS="$2"
      shift 2
      ;;
    --help)
      echo "Usage: $0 [options]"
      echo ""
      echo "Options:"
      echo "  --skip-cluster        Skip cluster creation"
      echo "  --skip-build          Skip image building"
      echo "  --cluster-name NAME   Name for kind cluster (default: drl-scheduler-demo)"
      echo "  --num-workers N       Number of worker nodes (default: 3)"
      echo "  --help                Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

# Create kind cluster
if [ "$CREATE_CLUSTER" = true ]; then
  echo -e "\n${YELLOW}Creating kind cluster '${CLUSTER_NAME}' with ${NUM_WORKERS} workers...${NC}"

  # Check if cluster already exists
  if kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
    echo -e "${YELLOW}Cluster '${CLUSTER_NAME}' already exists. Delete it? (y/N)${NC}"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
      kind delete cluster --name ${CLUSTER_NAME}
    else
      echo -e "${YELLOW}Using existing cluster${NC}"
      CREATE_CLUSTER=false
    fi
  fi

  if [ "$CREATE_CLUSTER" = true ]; then
    # Create kind config
    cat > /tmp/kind-config.yaml <<EOF
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
EOF

    # Add worker nodes
    for i in $(seq 1 $NUM_WORKERS); do
      cat >> /tmp/kind-config.yaml <<EOF
  - role: worker
    kubeadmConfigPatches:
    - |
      kind: JoinConfiguration
      nodeRegistration:
        kubeletExtraArgs:
          node-labels: "node-role=worker,worker-id=worker-${i}"
EOF
    done

    # Create cluster
    kind create cluster --name ${CLUSTER_NAME} --config /tmp/kind-config.yaml

    if [ $? -eq 0 ]; then
      echo -e "${GREEN}✓ Cluster created successfully${NC}"
    else
      echo -e "${RED}✗ Cluster creation failed${NC}"
      exit 1
    fi

    # Verify cluster
    kubectl cluster-info --context kind-${CLUSTER_NAME}
    echo -e "\n${GREEN}Nodes:${NC}"
    kubectl get nodes
  fi
else
  echo -e "\n${YELLOW}Skipping cluster creation${NC}"
fi

# Build and load image
if [ "$BUILD_IMAGE" = true ]; then
  echo -e "\n${YELLOW}Building scheduler image...${NC}"

  cd "$(dirname "$0")"

  docker build -t ${IMAGE_NAME}:${IMAGE_TAG} .

  if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Image built successfully${NC}"
  else
    echo -e "${RED}✗ Image build failed${NC}"
    exit 1
  fi

  # Load image into kind
  echo -e "\n${YELLOW}Loading image into kind cluster...${NC}"
  kind load docker-image ${IMAGE_NAME}:${IMAGE_TAG} --name ${CLUSTER_NAME}

  if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Image loaded successfully${NC}"

    # Verify image
    echo -e "\n${YELLOW}Verifying image in cluster...${NC}"
    docker exec -it ${CLUSTER_NAME}-control-plane crictl images | grep ${IMAGE_NAME} || true
  else
    echo -e "${RED}✗ Image loading failed${NC}"
    exit 1
  fi
else
  echo -e "\n${YELLOW}Skipping image build${NC}"
fi

# Deploy scheduler
if [ "$DEPLOY_SCHEDULER" = true ]; then
  echo -e "\n${YELLOW}Deploying DRL Scheduler...${NC}"

  # Create namespace
  kubectl create namespace drl-scheduler-system --dry-run=client -o yaml | kubectl apply -f -

  # Prepare manifest for kind
  MANIFEST_PATH="../../kubernetes-manifests/drl-scheduler.yaml"
  TEMP_MANIFEST="/tmp/drl-scheduler-kind.yaml"

  cat ${MANIFEST_PATH} | \
    sed "s|image: gcr.io/PROJECT_ID/drl-scheduler:latest|image: ${IMAGE_NAME}:${IMAGE_TAG}|g" | \
    sed 's|imagePullPolicy: Always|imagePullPolicy: IfNotPresent|g' | \
    sed 's|cpu: 2000m|cpu: 1000m|g' | \
    sed 's|memory: 4Gi|memory: 2Gi|g' | \
    sed 's|cpu: 500m|cpu: 250m|g' | \
    sed 's|memory: 1Gi|memory: 512Mi|g' > ${TEMP_MANIFEST}

  # Apply manifest
  kubectl apply -f ${TEMP_MANIFEST}

  if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Deployed successfully${NC}"
  else
    echo -e "${RED}✗ Deployment failed${NC}"
    exit 1
  fi

  # Wait for deployment
  echo -e "\n${YELLOW}Waiting for scheduler to be ready...${NC}"
  kubectl wait --for=condition=available --timeout=300s \
    deployment/drl-scheduler -n drl-scheduler-system

  if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Scheduler is ready${NC}"
  else
    echo -e "${RED}✗ Scheduler failed to become ready${NC}"
    echo -e "${YELLOW}Check logs with: kubectl logs -n drl-scheduler-system -l app=drl-scheduler${NC}"
    exit 1
  fi
fi

# Display status
echo -e "\n${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Deployment Complete!                                  ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"

echo -e "\n${GREEN}Cluster Information:${NC}"
kubectl cluster-info --context kind-${CLUSTER_NAME}

echo -e "\n${GREEN}Nodes:${NC}"
kubectl get nodes

echo -e "\n${GREEN}Scheduler Status:${NC}"
kubectl get pods -n drl-scheduler-system

echo -e "\n${GREEN}Services:${NC}"
kubectl get svc -n drl-scheduler-system

echo -e "\n${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Next Steps                                            ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"

echo -e "\n${YELLOW}1. View scheduler logs:${NC}"
echo -e "   ${GREEN}kubectl logs -n drl-scheduler-system -l app=drl-scheduler -f${NC}"

echo -e "\n${YELLOW}2. Access scheduler API:${NC}"
echo -e "   ${GREEN}kubectl port-forward -n drl-scheduler-system svc/drl-scheduler 8000:8000${NC}"
echo -e "   ${GREEN}curl http://localhost:8000/status | jq${NC}"

echo -e "\n${YELLOW}3. Deploy Online Boutique:${NC}"
echo -e "   ${GREEN}cd ../.. && kubectl apply -f release/kubernetes-manifests.yaml${NC}"

echo -e "\n${YELLOW}4. Update a service to use DRL scheduler:${NC}"
echo -e "   ${GREEN}kubectl patch deployment frontend \\${NC}"
echo -e "   ${GREEN}  -p '{\"spec\":{\"template\":{\"spec\":{\"schedulerName\":\"drl-scheduler\"}}}}'${NC}"

echo -e "\n${YELLOW}5. Monitor scheduling:${NC}"
echo -e "   ${GREEN}kubectl get events --watch | grep -i scheduled${NC}"

echo -e "\n${YELLOW}6. Check pod distribution:${NC}"
echo -e "   ${GREEN}kubectl get pods -o wide${NC}"

echo -e "\n${YELLOW}7. Run example script:${NC}"
echo -e "   ${GREEN}python examples/usage_example.py${NC}"

echo -e "\n${BLUE}For cleanup:${NC}"
echo -e "   ${GREEN}kind delete cluster --name ${CLUSTER_NAME}${NC}"

echo -e "\n${GREEN}Happy scheduling! 🚀${NC}\n"
