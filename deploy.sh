#!/bin/bash

# Cloud Run Deployment Script
# Usage: ./deploy.sh

PROJECT_ID="summer-presence-480823-h1"
REGION="us-central1"
SERVICE_NAME="applied-agent-service"

echo "🚀 Deploying $SERVICE_NAME to Cloud Run (Project: $PROJECT_ID)..."

# Deploy from source
# This uploads the code to Cloud Build, builds the container, and deploys it.
# It preserves existing environment variables set in the Console.
gcloud run deploy $SERVICE_NAME \
  --source . \
  --project $PROJECT_ID \
  --region $REGION \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 3600

echo "✅ Deployment complete!"
