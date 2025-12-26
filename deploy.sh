#!/bin/bash

# Production Deployment Script for Contabo VPS
# Run this script on your server after uploading the project files

set -e  # Exit on any error

echo "🚀 Starting deployment of Video Generation Application..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   print_error "This script should not be run as root for security reasons"
   exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    print_error ".env file not found!"
    print_warning "Please copy .env.production to .env and update with your values"
    exit 1
fi

# Update system packages
print_status "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    print_status "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
    print_warning "Please log out and log back in for Docker permissions to take effect"
fi

# Install Docker Compose if not present
if ! command -v docker-compose &> /dev/null; then
    print_status "Installing Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# Setup firewall
print_status "Configuring firewall..."
sudo ufw --force enable
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw allow 8080/tcp # API Gateway (alternative port)
sudo ufw allow 15672/tcp # RabbitMQ Management (optional, can be removed for security)
sudo ufw allow 9001/tcp  # MinIO Console (optional, can be removed for security)

# Create necessary directories
print_status "Creating necessary directories..."
mkdir -p logs
mkdir -p backups

# Stop existing containers if any
print_status "Stopping existing containers..."
docker-compose -f docker-compose.prod.yml down 2>/dev/null || true

# Pull latest images
print_status "Pulling latest base images..."
docker-compose -f docker-compose.prod.yml pull 2>/dev/null || true

# Build and start services
print_status "Building and starting services..."
docker-compose -f docker-compose.prod.yml up -d --build

# Wait for services to be healthy
print_status "Waiting for services to be healthy..."
sleep 30

# Check service status
print_status "Checking service status..."
docker-compose -f docker-compose.prod.yml ps

# Test API Gateway
print_status "Testing API Gateway..."
sleep 10
if curl -f http://localhost/health > /dev/null 2>&1; then
    print_status "✅ API Gateway is responding!"
else
    print_warning "⚠️  API Gateway might still be starting up..."
fi

# Setup log rotation
print_status "Setting up log rotation..."
sudo tee /etc/logrotate.d/docker-vide-gen > /dev/null <<EOF
/var/lib/docker/containers/*/*-json.log {
    rotate 7
    daily
    compress
    size 10M
    missingok
    delaycompress
    copytruncate
}
EOF

# Create backup script
print_status "Creating backup script..."
cat > backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p backups

# Backup database
docker exec vide_gen-postgres-1 pg_dump -U postgres vide_gen | gzip > backups/postgres_$DATE.sql.gz

# Backup MinIO data
docker exec vide_gen-minio-1 tar czf - /data | cat > backups/minio_$DATE.tar.gz

# Keep only last 7 backups
find backups/ -name "*.gz" -mtime +7 -delete

echo "Backup completed: $DATE"
EOF

chmod +x backup.sh

# Setup daily backup cron job
print_status "Setting up daily backups..."
(crontab -l 2>/dev/null; echo "0 2 * * * $(pwd)/backup.sh >> logs/backup.log 2>&1") | crontab -

print_status "🎉 Deployment completed successfully!"
echo ""
echo "📋 Deployment Summary:"
echo "===================="
echo "• Application URL: http://$(curl -s ifconfig.me || hostname -I | cut -d' ' -f1)"
echo "• API Gateway: Port 80"
echo "• RabbitMQ Management: Port 15672"
echo "• MinIO Console: Port 9001"
echo ""
echo "📁 Important files:"
echo "• Logs: ./logs/"
echo "• Backups: ./backups/"
echo "• Environment: ./.env"
echo ""
echo "🔧 Useful commands:"
echo "• View logs: docker-compose -f docker-compose.prod.yml logs -f [service]"
echo "• Restart service: docker-compose -f docker-compose.prod.yml restart [service]"
echo "• Stop all: docker-compose -f docker-compose.prod.yml down"
echo "• Start all: docker-compose -f docker-compose.prod.yml up -d"
echo "• Manual backup: ./backup.sh"
echo ""
print_warning "Remember to:"
print_warning "1. Update your domain DNS to point to this server"
print_warning "2. Set up SSL certificates (Let's Encrypt recommended)"
print_warning "3. Configure monitoring and alerting"
print_warning "4. Regularly check logs and backups"