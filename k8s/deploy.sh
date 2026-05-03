#!/bin/bash
# Deploy LLM Traffic Controller to Kubernetes
set -euo pipefail

NAMESPACE="traffic-agent"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚦 Deploying LLM Traffic Controller to Kubernetes..."

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl not found. Install it first."
    exit 1
fi

# Check if LONGCAT_API_KEY is set
if [ -z "${LONGCAT_API_KEY:-}" ]; then
    echo "⚠️  LONGCAT_API_KEY not set. Using placeholder."
    export LONGCAT_API_KEY="replace-with-your-key"
fi

# Build Docker image
echo "📦 Building Docker image..."
docker build -t traffic-agent:latest "$SCRIPT_DIR/.."

# If using minikube, load the image
if command -v minikube &> /dev/null && minikube status &> /dev/null 2>&1; then
    echo "🔄 Loading image into minikube..."
    minikimage load traffic-agent:latest
fi

# Apply K8s manifests
echo "🚀 Applying Kubernetes manifests..."
kubectl apply -k "$SCRIPT_DIR/"

# Wait for deployment
echo "⏳ Waiting for deployment to be ready..."
kubectl -n "$NAMESPACE" rollout status deployment/traffic-agent --timeout=120s

# Get service URL
echo ""
echo "✅ Deployment complete!"
echo ""
echo "📊 Dashboard:"
SERVICE_IP=$(kubectl -n "$NAMESPACE" get svc traffic-agent -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "pending")
if [ "$SERVICE_IP" = "pending" ] || [ -z "$SERVICE_IP" ]; then
    echo "   Service is getting an external IP..."
    echo "   Run: kubectl -n $NAMESPACE get svc traffic-agent"
    echo "   Or use port-forward:"
    echo "   kubectl -n $NAMESPACE port-forward svc/traffic-agent 8080:80"
else
    echo "   http://${SERVICE_IP}"
fi
echo ""
echo "📋 Useful commands:"
echo "   kubectl -n $NAMESPACE get pods"
echo "   kubectl -n $NAMESPACE logs -f deployment/traffic-agent"
echo "   kubectl -n $NAMESPACE delete -k $SCRIPT_DIR/"
