#!/bin/bash
# =============================================================================
# Google Cloud e2-micro Setup Script
# Polymarket Trading Bot - FREE TIER
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=============================================="
echo "🚀 Polymarket Bot - GCloud Setup"
echo "=============================================="

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}❌ gcloud CLI not installed${NC}"
    echo ""
    echo "Install it from: https://cloud.google.com/sdk/docs/install"
    echo ""
    echo "Quick install (Linux/Mac):"
    echo "  curl https://sdk.cloud.google.com | bash"
    echo "  exec -l \$SHELL"
    echo "  gcloud init"
    exit 1
fi

echo -e "${GREEN}✓ gcloud CLI found${NC}"

# Check authentication
echo ""
echo "Checking GCloud authentication..."
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -1 > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠ Not logged in. Running gcloud auth login...${NC}"
    gcloud auth login
fi

ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -1)
echo -e "${GREEN}✓ Logged in as: $ACCOUNT${NC}"

# Get or create project
echo ""
echo "Checking project..."
PROJECT_ID=$(gcloud config get-value project 2>/dev/null)

if [ -z "$PROJECT_ID" ]; then
    echo -e "${YELLOW}No project set. Creating new project...${NC}"
    PROJECT_ID="polymarket-bot-$(date +%s)"
    gcloud projects create $PROJECT_ID --name="Polymarket Bot"
    gcloud config set project $PROJECT_ID
fi

echo -e "${GREEN}✓ Using project: $PROJECT_ID${NC}"

# Enable required APIs
echo ""
echo "Enabling required APIs..."
gcloud services enable compute.googleapis.com --quiet
echo -e "${GREEN}✓ Compute Engine API enabled${NC}"

# Set zone (free tier regions)
ZONE="us-central1-a"
echo ""
echo -e "${GREEN}✓ Using zone: $ZONE (free tier eligible)${NC}"

# Check if VM already exists
VM_NAME="polymarket-bot"
if gcloud compute instances describe $VM_NAME --zone=$ZONE &> /dev/null; then
    echo -e "${YELLOW}⚠ VM '$VM_NAME' already exists${NC}"
    echo "Delete it first with: gcloud compute instances delete $VM_NAME --zone=$ZONE"
    exit 1
fi

# Create the VM
echo ""
echo "Creating e2-micro VM (FREE TIER)..."
gcloud compute instances create $VM_NAME \
    --zone=$ZONE \
    --machine-type=e2-micro \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=30GB \
    --boot-disk-type=pd-standard \
    --tags=http-server,https-server \
    --metadata=startup-script='#!/bin/bash
apt-get update
apt-get install -y python3-pip python3-venv git
'

echo -e "${GREEN}✓ VM created successfully!${NC}"

# Create firewall rules
echo ""
echo "Setting up firewall rules..."
gcloud compute firewall-rules create allow-http \
    --allow tcp:80,tcp:8000,tcp:8080,tcp:443 \
    --target-tags=http-server,https-server \
    --description="Allow HTTP/HTTPS traffic" \
    --quiet 2>/dev/null || echo "Firewall rule already exists"

echo -e "${GREEN}✓ Firewall configured${NC}"

# Get external IP
EXTERNAL_IP=$(gcloud compute instances describe $VM_NAME --zone=$ZONE --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

echo ""
echo "=============================================="
echo -e "${GREEN}🎉 SUCCESS! Your VM is ready!${NC}"
echo "=============================================="
echo ""
echo "VM Name:     $VM_NAME"
echo "Zone:        $ZONE"
echo "External IP: $EXTERNAL_IP"
echo ""
echo "Next steps:"
echo ""
echo "1. SSH into your VM:"
echo "   gcloud compute ssh $VM_NAME --zone=$ZONE"
echo ""
echo "2. Clone your repo and set up:"
echo "   git clone https://github.com/LPTravelAustralia/polymarket.git"
echo "   cd polymarket"
echo "   pip3 install -r requirements.txt"
echo "   pip3 install -r backend/requirements.txt"
echo ""
echo "3. Create your .env file with API keys"
echo ""
echo "4. Run the bot:"
echo "   cd backend && python3 main.py"
echo ""
echo "Your API will be available at: http://$EXTERNAL_IP:8000"
echo ""
