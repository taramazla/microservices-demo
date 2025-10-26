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

# Build and deploy DRL Scheduler

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}DRL Scheduler Build & Deploy Script${NC}"
echo "======================================"

# Check prerequisites
command -v docker >/dev/null 2>&1 || { echo -e "${RED}Docker is required but not installed.${NC}" >&2; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo -e "${RED}kubectl is required but not installed.${NC}" >&2; exit 1; }

# Configuration
IMAGE_NAME="drl-scheduler"
IMAGE_TAG=${IMAGE_TAG:-"v1.0"}
PROJECT_ID=${PROJECT_ID:-""}
REGISTRY=${REGISTRY:-"gcr.io"}

# Parse arguments
BUILD_ONLY=false
DEPLOY_ONLY=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --build-only)
      BUILD_ONLY=true
      shift
      ;;
    --deploy-only)
      DEPLOY_ONLY=true
      shift
      ;;
    --project-id)
      PROJECT_ID="$2"
      shift 2
      ;;
    --image-tag)
      IMAGE_TAG="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--build-only] [--deploy-only] [--project-id PROJECT_ID] [--image-tag TAG]"
      exit 1
      ;;
  esac
done

# Build image
if [ "$DEPLOY_ONLY" = false ]; then
  echo -e "\n${YELLOW}Building Docker image...${NC}"

  cd "$(dirname "$0")"

  docker build -t ${IMAGE_NAME}:${IMAGE_TAG} .

  if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Image built successfully${NC}"
  else
    echo -e "${RED}✗ Image build failed${NC}"
    exit 1
  fi

  # Push to registry if PROJECT_ID is set
  if [ -n "$PROJECT_ID" ]; then
    echo -e "\n${YELLOW}Pushing image to ${REGISTRY}...${NC}"

    FULL_IMAGE="${REGISTRY}/${PROJECT_ID}/${IMAGE_NAME}:${IMAGE_TAG}"

    docker tag ${IMAGE_NAME}:${IMAGE_TAG} ${FULL_IMAGE}
    docker push ${FULL_IMAGE}

    if [ $? -eq 0 ]; then
      echo -e "${GREEN}✓ Image pushed successfully${NC}"
    else
      echo -e "${RED}✗ Image push failed${NC}"
      exit 1
    fi
  fi
fi

# Deploy to Kubernetes
if [ "$BUILD_ONLY" = false ]; then
  echo -e "\n${YELLOW}Deploying to Kubernetes...${NC}"

  # Check if cluster is accessible
  kubectl cluster-info > /dev/null 2>&1
  if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Cannot connect to Kubernetes cluster${NC}"
    exit 1
  fi

  # Create namespace
  kubectl create namespace drl-scheduler-system --dry-run=client -o yaml | kubectl apply -f -

  # Update image in manifest
  MANIFEST_PATH="../../kubernetes-manifests/drl-scheduler.yaml"

  if [ -n "$PROJECT_ID" ]; then
    FULL_IMAGE="${REGISTRY}/${PROJECT_ID}/${IMAGE_NAME}:${IMAGE_TAG}"
    sed -i.bak "s|image: gcr.io/PROJECT_ID/drl-scheduler:latest|image: ${FULL_IMAGE}|g" ${MANIFEST_PATH}
  else
    sed -i.bak "s|image: gcr.io/PROJECT_ID/drl-scheduler:latest|image: ${IMAGE_NAME}:${IMAGE_TAG}|g" ${MANIFEST_PATH}
    sed -i.bak "s|imagePullPolicy: Always|imagePullPolicy: IfNotPresent|g" ${MANIFEST_PATH}
  fi

  # Apply manifest
  kubectl apply -f ${MANIFEST_PATH}

  # Restore original manifest
  mv ${MANIFEST_PATH}.bak ${MANIFEST_PATH}

  if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Deployed successfully${NC}"
  else
    echo -e "${RED}✗ Deployment failed${NC}"
    exit 1
  fi

  # Wait for deployment
  echo -e "\n${YELLOW}Waiting for deployment to be ready...${NC}"
  kubectl wait --for=condition=available --timeout=300s \
    deployment/drl-scheduler -n drl-scheduler-system

  if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Deployment is ready${NC}"

    # Display status
    echo -e "\n${YELLOW}Deployment Status:${NC}"
    kubectl get pods -n drl-scheduler-system

    echo -e "\n${YELLOW}Service endpoints:${NC}"
    kubectl get svc -n drl-scheduler-system

    echo -e "\n${GREEN}Scheduler is now running!${NC}"
    echo -e "View logs with: ${YELLOW}kubectl logs -n drl-scheduler-system -l app=drl-scheduler -f${NC}"
    echo -e "Access API with: ${YELLOW}kubectl port-forward -n drl-scheduler-system svc/drl-scheduler 8000:8000${NC}"

  else
    echo -e "${RED}✗ Deployment failed to become ready${NC}"
    echo -e "Check logs with: kubectl logs -n drl-scheduler-system -l app=drl-scheduler"
    exit 1
  fi
fi

echo -e "\n${GREEN}Done!${NC}"
