# Contabo VPS Deployment Guide

## 🚀 Quick Deployment Steps

### 1. Server Requirements
- **Minimum**: 4 vCPU, 8GB RAM, 100GB SSD
- **Recommended**: 8 vCPU, 16GB RAM, 200GB SSD
- **OS**: Ubuntu 20.04 LTS or 22.04 LTS

### 2. Upload Project to Server

```bash
# On your local machine, create a tar file
tar -czf vide_gen.tar.gz --exclude='node_modules' --exclude='.git' --exclude='__pycache__' .

# Upload to server (replace YOUR_SERVER_IP)
scp vide_gen.tar.gz root@YOUR_SERVER_IP:/root/

# SSH into server
ssh root@YOUR_SERVER_IP

# Extract files
cd /root
tar -xzf vide_gen.tar.gz
cd vide_gen
```

### 3. Configure Environment

```bash
# Copy production environment template
cp .env.production .env

# Edit environment file with your actual values
nano .env
```

**Required values to update in .env:**
```env
POSTGRES_PASSWORD=your_secure_postgres_password_here
RABBITMQ_PASSWORD=your_secure_rabbitmq_password_here
MINIO_ROOT_PASSWORD=your_secure_minio_password_here
JWT_SECRET_KEY=your-super-secure-jwt-key-for-production
OPENAI_API_KEY=your_openai_api_key_here
GOOGLE_AI_API_KEY=AIzaSyBZeMF5vc1fsMmsQ6_jfFzYvYQkl8A97Xk
```

### 4. Run Deployment Script

```bash
# Make script executable and run
chmod +x deploy.sh
./deploy.sh
```

### 5. Verify Deployment

After deployment completes, check:

```bash
# Check all services are running
docker-compose -f docker-compose.prod.yml ps

# Test API endpoint
curl http://localhost/health

# Check logs if needed
docker-compose -f docker-compose.prod.yml logs api-gateway
```

## 🌐 Access Your Application

- **API Gateway**: http://YOUR_SERVER_IP
- **RabbitMQ Management**: http://YOUR_SERVER_IP:15672
- **MinIO Console**: http://YOUR_SERVER_IP:9001

## 🔧 Server Management Commands

### Service Management
```bash
# View all services status
docker-compose -f docker-compose.prod.yml ps

# Restart a specific service
docker-compose -f docker-compose.prod.yml restart api-gateway

# View logs
docker-compose -f docker-compose.prod.yml logs -f api-gateway

# Stop all services
docker-compose -f docker-compose.prod.yml down

# Start all services
docker-compose -f docker-compose.prod.yml up -d
```

### Monitoring & Maintenance
```bash
# Check system resources
htop
df -h

# View Docker system usage
docker system df

# Clean up unused Docker resources
docker system prune -f

# Manual backup
./backup.sh

# View backup logs
tail -f logs/backup.log
```

## 🔒 Security Configuration

### Firewall Rules (Already configured by script)
- Port 22: SSH access
- Port 80: HTTP traffic
- Port 443: HTTPS traffic
- Port 15672: RabbitMQ Management (optional)
- Port 9001: MinIO Console (optional)

### Recommended Security Steps

1. **Change SSH port** (optional):
```bash
sudo nano /etc/ssh/sshd_config
# Change Port 22 to Port 2222
sudo systemctl restart ssh
# Update firewall: sudo ufw allow 2222/tcp
```

2. **Disable root login**:
```bash
# Create a new user first
adduser yourusername
usermod -aG sudo yourusername
# Then disable root login in SSH config
```

3. **Set up fail2ban**:
```bash
sudo apt install fail2ban -y
sudo systemctl enable fail2ban
```

## 🌟 Domain & SSL Setup

### 1. Point Domain to Server
- Update your domain's DNS A record to point to your server IP
- Wait for DNS propagation (may take up to 24 hours)

### 2. Install SSL Certificate (Recommended)
```bash
# Install Certbot
sudo apt install certbot nginx -y

# Configure Nginx as reverse proxy
sudo nano /etc/nginx/sites-available/vide-gen
```

Create Nginx configuration:
```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Enable site and get SSL
sudo ln -s /etc/nginx/sites-available/vide-gen /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Get SSL certificate
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

## 📊 Monitoring Setup

### Check Application Health
```bash
# API Gateway health check
curl http://localhost/health

# Database connection
docker exec vide_gen-postgres-1 pg_isready -U postgres

# Redis connection
docker exec vide_gen-redis-1 redis-cli ping

# MinIO health
curl http://localhost:9000/minio/health/live
```

### Log Monitoring
```bash
# View all container logs
docker-compose -f docker-compose.prod.yml logs

# Follow specific service logs
docker-compose -f docker-compose.prod.yml logs -f api-gateway

# Check system logs
sudo journalctl -f
```

## 🆘 Troubleshooting

### Common Issues

1. **Services not starting**:
```bash
# Check logs for errors
docker-compose -f docker-compose.prod.yml logs

# Check system resources
free -h
df -h
```

2. **API not responding**:
```bash
# Check if container is running
docker ps | grep api-gateway

# Check container logs
docker logs vide_gen-api-gateway-1

# Restart service
docker-compose -f docker-compose.prod.yml restart api-gateway
```

3. **Database connection issues**:
```bash
# Check PostgreSQL logs
docker logs vide_gen-postgres-1

# Test database connection
docker exec vide_gen-postgres-1 psql -U postgres -d vide_gen -c "SELECT 1;"
```

### Recovery Procedures

1. **Restore from backup**:
```bash
# List available backups
ls -la backups/

# Restore database
gunzip -c backups/postgres_YYYYMMDD_HHMMSS.sql.gz | docker exec -i vide_gen-postgres-1 psql -U postgres -d vide_gen
```

2. **Complete restart**:
```bash
# Stop everything
docker-compose -f docker-compose.prod.yml down

# Clean up
docker system prune -f

# Start fresh
docker-compose -f docker-compose.prod.yml up -d --build
```

## 📞 Support Information

Your application is now deployed! For additional help:

1. Check logs: `docker-compose -f docker-compose.prod.yml logs`
2. Monitor resources: `htop` and `df -h`
3. Review backups: `ls -la backups/`

**Important**: Save your `.env` file and server credentials securely!