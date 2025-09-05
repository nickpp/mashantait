#!/bin/bash

# Setup Nginx proxy for משכנתאית 2026
# Run this script on your server

set -e

# Configuration
DOMAIN="maskantait.commentiq.ai"
APP_PORT="8080"
NGINX_SITE="mashantait"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🌐 Setting up Nginx proxy for משכנתאית 2026${NC}"
echo "Domain: $DOMAIN"
echo "App Port: $APP_PORT"
echo "=================================================="

echo -e "${YELLOW}📋 Step 1: Installing Nginx (if not installed)...${NC}"
sudo apt update
sudo apt install -y nginx

echo -e "${YELLOW}🔧 Step 2: Creating Nginx configuration...${NC}"

# Create nginx configuration
sudo tee /etc/nginx/sites-available/$NGINX_SITE > /dev/null << EOF
server {
    listen 80;
    server_name $DOMAIN;

    # Serve static files directly
    location /static/ {
        alias $(pwd)/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Proxy all requests to FastAPI
    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # WebSocket support
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

    # Logs
    access_log /var/log/nginx/mashantait_access.log;
    error_log /var/log/nginx/mashantait_error.log;
}
EOF

echo -e "${YELLOW}🔗 Step 3: Enabling the site...${NC}"
# Enable the site
sudo ln -sf /etc/nginx/sites-available/$NGINX_SITE /etc/nginx/sites-enabled/

# Remove default site if it exists
sudo rm -f /etc/nginx/sites-enabled/default

echo -e "${YELLOW}🧪 Step 4: Testing Nginx configuration...${NC}"
sudo nginx -t

echo -e "${YELLOW}🔄 Step 5: Reloading Nginx...${NC}"
sudo systemctl reload nginx
sudo systemctl enable nginx

echo -e "${GREEN}✅ Nginx proxy setup completed!${NC}"
echo "=================================================="
echo -e "${BLUE}🏛️ משכנתאית 2026 will be accessible at:${NC}"
echo -e "${GREEN}   http://$DOMAIN${NC}"
echo ""
echo -e "${YELLOW}📋 Next steps:${NC}"
echo "1. Make sure your app is running on port $APP_PORT"
echo "2. Point DNS $DOMAIN to this server's IP"
echo "3. Setup SSL with: sudo certbot --nginx -d $DOMAIN"
echo ""
echo -e "${YELLOW}🔧 Useful commands:${NC}"
echo "   Check nginx status: sudo systemctl status nginx"
echo "   View nginx logs:    sudo tail -f /var/log/nginx/mashantait_*.log"
echo "   Test configuration: sudo nginx -t"
echo "   Reload nginx:       sudo systemctl reload nginx"
