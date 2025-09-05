#!/bin/bash

# Deploy משכנתאית 2026 - Israeli Mortgage Engine
# This script deploys the application to a server with nginx

set -e  # Exit on any error

# Configuration - UPDATE THESE VALUES
SERVER_HOST="your-server.com"
SERVER_USER="deploy"
REPO_URL="https://github.com/nickpp/mashantait.git"
APP_NAME="mashantait"
APP_DIR="/var/www/$APP_NAME"
SERVICE_NAME="mashantait"
PYTHON_VERSION="python3.12"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🏛️ Deploying משכנתאית 2026 to $SERVER_HOST${NC}"
echo "=================================================="

# Function to run commands on server
run_remote() {
    ssh -t "$SERVER_USER@$SERVER_HOST" "$1"
}

# Function to copy files to server
copy_to_server() {
    scp "$1" "$SERVER_USER@$SERVER_HOST:$2"
}

echo -e "${YELLOW}📋 Step 1: Preparing server environment...${NC}"

# Create application directory and setup
run_remote "
    sudo mkdir -p $APP_DIR
    sudo chown $USER:$USER $APP_DIR
    cd $APP_DIR
    
    # Clone or update repository
    if [ -d '.git' ]; then
        echo '🔄 Updating existing repository...'
        git pull origin main
    else
        echo '📥 Cloning repository...'
        git clone $REPO_URL .
    fi
"

echo -e "${YELLOW}🐍 Step 2: Setting up Python environment...${NC}"

run_remote "
    cd $APP_DIR
    
    # Create virtual environment
    if [ ! -d 'venv' ]; then
        echo '🔧 Creating virtual environment...'
        $PYTHON_VERSION -m venv venv
    fi
    
    # Activate and install dependencies
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    
    # Test the application
    echo '🧪 Testing application...'
    python -c 'import main; print(\"✅ Application imports successfully\")'
"

echo -e "${YELLOW}⚙️ Step 3: Creating systemd service...${NC}"

# Create systemd service file locally
cat > mashantait.service << EOF
[Unit]
Description=משכנתאית 2026 - Israeli Mortgage Engine
After=network.target

[Service]
Type=simple
User=$SERVER_USER
WorkingDirectory=$APP_DIR
Environment=PATH=$APP_DIR/venv/bin
ExecStart=$APP_DIR/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Copy service file to server
copy_to_server "mashantait.service" "/tmp/mashantait.service"

# Install and start service
run_remote "
    sudo mv /tmp/mashantait.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable $SERVICE_NAME
    sudo systemctl restart $SERVICE_NAME
    
    # Check service status
    echo '📊 Service status:'
    sudo systemctl status $SERVICE_NAME --no-pager
"

echo -e "${YELLOW}🌐 Step 4: Configuring nginx...${NC}"

# Create nginx configuration locally
cat > mashantait.nginx << EOF
server {
    listen 80;
    server_name $SERVER_HOST;

    # Serve static files directly
    location /static/ {
        alias $APP_DIR/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Proxy API requests to FastAPI
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # WebSocket support (if needed)
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/xml+rss application/json;
}
EOF

# Copy nginx config to server
copy_to_server "mashantait.nginx" "/tmp/mashantait.nginx"

# Install nginx configuration
run_remote "
    sudo mv /tmp/mashantait.nginx /etc/nginx/sites-available/$APP_NAME
    sudo ln -sf /etc/nginx/sites-available/$APP_NAME /etc/nginx/sites-enabled/
    
    # Test nginx configuration
    sudo nginx -t
    
    # Reload nginx
    sudo systemctl reload nginx
"

echo -e "${YELLOW}🔒 Step 5: Setting up SSL (optional)...${NC}"
echo "To setup SSL with Let's Encrypt, run on the server:"
echo "sudo apt install certbot python3-certbot-nginx"
echo "sudo certbot --nginx -d $SERVER_HOST"

echo -e "${GREEN}✅ Deployment completed successfully!${NC}"
echo "=================================================="
echo -e "${BLUE}🏛️ משכנתאית 2026 is now running at:${NC}"
echo -e "${GREEN}   http://$SERVER_HOST${NC}"
echo ""
echo -e "${YELLOW}📋 Useful commands:${NC}"
echo "   Check service: ssh $SERVER_USER@$SERVER_HOST 'sudo systemctl status $SERVICE_NAME'"
echo "   View logs:     ssh $SERVER_USER@$SERVER_HOST 'sudo journalctl -u $SERVICE_NAME -f'"
echo "   Restart app:   ssh $SERVER_USER@$SERVER_HOST 'sudo systemctl restart $SERVICE_NAME'"
echo "   Update code:   ./deploy_mortgage.sh"

# Cleanup local files
rm -f mashantait.service mashantait.nginx

echo -e "${GREEN}🎉 Deploy script completed!${NC}"
