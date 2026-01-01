#!/bin/bash
# =============================================================================
# Server Setup Script - Run this ON the GCloud VM after SSH
# =============================================================================

set -e

echo "=============================================="
echo "🔧 Setting up Polymarket Bot on GCloud VM"
echo "=============================================="

# Update system
echo "Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Install Python and dependencies
echo "Installing Python..."
sudo apt-get install -y python3 python3-pip python3-venv git nginx

# Create app directory
echo "Setting up application..."
mkdir -p ~/polymarket
cd ~/polymarket

# Clone repository (if not already cloned)
if [ ! -d ".git" ]; then
    git clone https://github.com/LPTravelAustralia/polymarket.git .
fi

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install -r backend/requirements.txt

# Create .env template
if [ ! -f ".env" ]; then
    cat > .env << 'EOF'
# Polymarket API Credentials
POLYGON_WALLET_PRIVATE_KEY=your_private_key_here
POLYMARKET_API_KEY=your_api_key_here
POLYMARKET_API_SECRET=your_api_secret_here
POLYMARKET_PASSPHRASE=your_passphrase_here

# OpenAI for AI predictions
OPENAI_API_KEY=your_openai_key_here

# Fee collection (optional)
FEE_WALLET_ADDRESS=your_fee_wallet_here
FEE_PERCENTAGE=0.001

# Bot settings
USE_AI_PREDICTIONS=true
LOG_LEVEL=INFO
MONITORING_INTERVAL=60
EOF
    echo ""
    echo "⚠️  Created .env template - EDIT IT with your real keys!"
    echo "    nano .env"
fi

# Create systemd service for auto-start
sudo tee /etc/systemd/system/polymarket-bot.service > /dev/null << EOF
[Unit]
Description=Polymarket Trading Bot API
After=network.target

[Service]
User=$USER
WorkingDirectory=$HOME/polymarket/backend
Environment="PATH=$HOME/polymarket/venv/bin"
EnvironmentFile=$HOME/polymarket/.env
ExecStart=$HOME/polymarket/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo ""
echo "=============================================="
echo "✅ Setup complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Edit your .env file with real API keys:"
echo "   nano ~/polymarket/.env"
echo ""
echo "2. Start the bot:"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable polymarket-bot"
echo "   sudo systemctl start polymarket-bot"
echo ""
echo "3. Check status:"
echo "   sudo systemctl status polymarket-bot"
echo ""
echo "4. View logs:"
echo "   sudo journalctl -u polymarket-bot -f"
echo ""
