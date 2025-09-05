#!/bin/bash

# Run משכנתאית 2026 locally on server
# This script sets up and runs the application directly on the server

set -e  # Exit on any error

# Configuration
APP_PORT="8080"
PYTHON_VERSION="python3"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🏛️ Setting up משכנתאית 2026 locally${NC}"
echo "=============================================="

echo -e "${YELLOW}🐍 Step 1: Setting up Python environment...${NC}"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON_VERSION -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip and install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo -e "${YELLOW}🧪 Step 2: Testing application...${NC}"
python -c "import main; print('✅ Application imports successfully')"

echo -e "${YELLOW}🚀 Step 3: Starting server...${NC}"
echo -e "${GREEN}משכנתאית 2026 will be available at:${NC}"
echo -e "${GREEN}   http://localhost:$APP_PORT${NC}"
echo -e "${GREEN}   http://$(hostname -I | awk '{print $1}'):$APP_PORT${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop the server${NC}"
echo "=============================================="

# Start the server
uvicorn main:app --host 0.0.0.0 --port $APP_PORT --reload
