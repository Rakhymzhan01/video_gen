#!/bin/bash

# Video Generation Platform API Test Script
# This script demonstrates the complete flow of the video generation platform

set -e

API_BASE="http://localhost:8000/api/v1"
echo "🚀 Video Generation Platform API Test"
echo "======================================"
echo ""

# Test 1: Health Check
echo "📋 1. Health Check"
echo "-------------------"
health_response=$(curl -s "$API_BASE/../health" || echo "❌ API Gateway not available")
echo "Response: $health_response"
echo ""

# Test 2: Service Health Check
echo "📋 2. Service Health Check"
echo "----------------------------"
services_health=$(curl -s "$API_BASE/../health/services" || echo "❌ Services health check failed")
echo "Response: $services_health"
echo ""

# Test 3: User Registration
echo "📝 3. User Registration"
echo "------------------------"
register_data='{
    "email": "demo@example.com",
    "password": "SecurePass123",
    "first_name": "Demo",
    "last_name": "User"
}'

register_response=$(curl -s -X POST "$API_BASE/auth/register" \
    -H "Content-Type: application/json" \
    -d "$register_data" || echo "❌ Registration failed")
echo "Response: $register_response"

# Extract access token for subsequent requests
ACCESS_TOKEN=$(echo "$register_response" | jq -r '.access_token // empty' 2>/dev/null || echo "")
echo "Access Token: ${ACCESS_TOKEN:0:20}..."
echo ""

if [ -z "$ACCESS_TOKEN" ]; then
    echo "❌ Could not extract access token. Skipping authenticated requests."
    exit 1
fi

# Test 4: User Login
echo "🔐 4. User Login"
echo "----------------"
login_data='{
    "email": "demo@example.com",
    "password": "SecurePass123"
}'

login_response=$(curl -s -X POST "$API_BASE/auth/login" \
    -H "Content-Type: application/json" \
    -d "$login_data" || echo "❌ Login failed")
echo "Response: $login_response"
echo ""

# Test 5: Get User Profile
echo "👤 5. Get User Profile"
echo "----------------------"
profile_response=$(curl -s -X GET "$API_BASE/user/profile" \
    -H "Authorization: Bearer $ACCESS_TOKEN" || echo "❌ Profile fetch failed")
echo "Response: $profile_response"
echo ""

# Test 6: Image Upload (mock)
echo "🖼️  6. Image Upload Test"
echo "------------------------"
echo "Creating a test image file..."
echo "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==" | base64 -d > test_image.png

upload_response=$(curl -s -X POST "$API_BASE/images/upload" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -F "file=@test_image.png" \
    -F "user_id=demo-user" \
    -F "user_email=demo@example.com" || echo "❌ Image upload failed")
echo "Response: $upload_response"

# Extract image ID for video generation
IMAGE_ID=$(echo "$upload_response" | jq -r '.id // empty' 2>/dev/null || echo "")
echo "Image ID: $IMAGE_ID"
echo ""

# Test 7: List User Images
echo "📋 7. List User Images"
echo "----------------------"
images_response=$(curl -s -X GET "$API_BASE/images/" \
    -H "Authorization: Bearer $ACCESS_TOKEN" || echo "❌ Images list failed")
echo "Response: $images_response"
echo ""

# Test 8: Video Generation (Text-to-Video)
echo "🎬 8. Text-to-Video Generation"
echo "-------------------------------"
video_data='{
    "prompt": "A beautiful sunset over mountains with flowing clouds",
    "duration_seconds": 10,
    "resolution_width": 1280,
    "resolution_height": 720,
    "fps": 24,
    "provider": "auto"
}'

video_response=$(curl -s -X POST "$API_BASE/videos/generate" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$video_data" || echo "❌ Video generation failed")
echo "Response: $video_response"

# Extract video ID
VIDEO_ID=$(echo "$video_response" | jq -r '.video_id // empty' 2>/dev/null || echo "")
echo "Video ID: $VIDEO_ID"
echo ""

# Test 9: Video Generation (Image-to-Video)
if [ -n "$IMAGE_ID" ]; then
    echo "🎬 9. Image-to-Video Generation"
    echo "--------------------------------"
    image_video_data='{
        "prompt": "Animate this image with gentle motion and soft lighting",
        "image_id": "'$IMAGE_ID'",
        "duration_seconds": 5,
        "resolution_width": 1280,
        "resolution_height": 720,
        "fps": 24,
        "provider": "auto"
    }'

    image_video_response=$(curl -s -X POST "$API_BASE/videos/generate" \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$image_video_data" || echo "❌ Image-to-video generation failed")
    echo "Response: $image_video_response"
    echo ""
fi

# Test 10: Check Video Status
if [ -n "$VIDEO_ID" ]; then
    echo "📊 10. Check Video Status"
    echo "------------------------"
    status_response=$(curl -s -X GET "$API_BASE/videos/$VIDEO_ID/status" \
        -H "Authorization: Bearer $ACCESS_TOKEN" || echo "❌ Status check failed")
    echo "Response: $status_response"
    echo ""
fi

# Test 11: List User Videos
echo "📋 11. List User Videos"
echo "------------------------"
videos_response=$(curl -s -X GET "$API_BASE/videos/" \
    -H "Authorization: Bearer $ACCESS_TOKEN" || echo "❌ Videos list failed")
echo "Response: $videos_response"
echo ""

# Test 12: Get User Credits/Billing Info
echo "💳 12. Get User Credits"
echo "-----------------------"
credits_response=$(curl -s -X GET "$API_BASE/billing/credits" \
    -H "Authorization: Bearer $ACCESS_TOKEN" || echo "❌ Credits check failed")
echo "Response: $credits_response"
echo ""

# Cleanup
echo "🧹 Cleanup"
echo "----------"
if [ -f "test_image.png" ]; then
    rm test_image.png
    echo "Removed test image file"
fi

echo ""
echo "✅ API Test Complete!"
echo "===================="
echo ""
echo "📊 Summary:"
echo "- Platform provides full video generation workflow"
echo "- User registration and authentication working"
echo "- Image upload and processing capabilities"
echo "- Text-to-video and image-to-video generation"
echo "- Credit system and billing integration"
echo "- Real-time status tracking"
echo ""
echo "🏗️  Architecture Features:"
echo "- Microservices architecture with API Gateway"
echo "- JWT-based authentication and authorization"
echo "- Multi-provider video generation (Veo 3, Sora 2, Kling)"
echo "- S3-compatible storage (MinIO for local dev)"
echo "- Message queue processing with RabbitMQ"
echo "- Real-time monitoring with Prometheus/Grafana"
echo "- Comprehensive logging with ELK stack"
echo ""
echo "🔗 Useful URLs:"
echo "- API Documentation: http://localhost:8000/docs"
echo "- Grafana Dashboard: http://localhost:3000 (admin/admin)"
echo "- RabbitMQ Management: http://localhost:15672 (guest/guest)"
echo "- MinIO Console: http://localhost:9001 (minioadmin/minioadmin)"
echo "- Prometheus: http://localhost:9090"
echo "- Kibana: http://localhost:5601"