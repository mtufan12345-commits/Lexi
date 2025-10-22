#!/bin/bash

# Lexi AI - Quick Deployment Script
# Dit script helpt met snelle deployment op een nieuwe server

set -e  # Exit on any error

echo "🚀 Lexi AI Deployment Script"
echo "================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${RED}❌ ERROR: .env file not found!${NC}"
    echo ""
    echo "Please create a .env file with all required environment variables."
    echo "You can copy .env.example as a template:"
    echo ""
    echo "  cp .env.example .env"
    echo "  nano .env  # Fill in all values"
    echo ""
    exit 1
fi

echo -e "${GREEN}✅ .env file found${NC}"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ ERROR: Docker is not installed!${NC}"
    echo ""
    echo "Install Docker first:"
    echo "  curl -fsSL https://get.docker.com -o get-docker.sh"
    echo "  sudo sh get-docker.sh"
    echo ""
    exit 1
fi

echo -e "${GREEN}✅ Docker is installed${NC}"

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ ERROR: Docker Compose is not installed!${NC}"
    echo ""
    echo "Install Docker Compose first:"
    echo "  sudo apt install docker-compose -y"
    echo ""
    exit 1
fi

echo -e "${GREEN}✅ Docker Compose is installed${NC}"
echo ""

# Build Docker image
echo "🐳 Building Docker image..."
docker-compose build --no-cache

# Stop any running containers
echo "🔄 Stopping old containers..."
docker-compose down

# Start containers
echo "🚀 Starting containers..."
docker-compose up -d

# Wait for application to start
echo "⏳ Waiting for application to start..."
sleep 15

# Check health endpoint
echo "🏥 Checking application health..."
if curl -f http://localhost:5000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Application is healthy!${NC}"
    echo ""
    echo "🎉 Deployment successful!"
    echo ""
    echo "Access your application at:"
    echo "  http://localhost:5000"
    echo ""
    echo "Useful commands:"
    echo "  docker-compose logs -f          # View logs"
    echo "  docker-compose ps               # Show containers"
    echo "  docker-compose restart          # Restart"
    echo "  docker-compose down             # Stop"
    echo ""
else
    echo -e "${RED}❌ Health check failed!${NC}"
    echo ""
    echo "Check logs with:"
    echo "  docker-compose logs -f"
    echo ""
    exit 1
fi

# Show running containers
echo "📊 Running containers:"
docker-compose ps
