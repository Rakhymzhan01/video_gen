#!/usr/bin/env python3
"""
Quick test to generate a video with fal.ai providers
"""
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Check if we have the API key
fal_key = os.getenv("FAL_KEY")
if not fal_key or fal_key == "your_fal_ai_api_key_here":
    print("❌ Please add your real FAL_KEY to the .env file!")
    print("1. Go to https://fal.ai/ and get your API key")
    print("2. Replace 'your_fal_ai_api_key_here' in .env with your actual key")
    exit(1)

print(f"✅ FAL_KEY found: {fal_key[:10]}...")

try:
    # Try to import our providers
    import sys
    sys.path.append('.')
    
    from shared.providers.kling_provider import KlingProvider
    from shared.providers.base import VideoGenerationRequest
    
    print("✅ Imports successful")
    
    async def test_generation():
        """Test actual video generation"""
        print("\n🎬 Testing video generation with Kling...")
        
        # Create provider
        provider = KlingProvider(api_key=fal_key)
        
        # Create request
        request = VideoGenerationRequest(
            prompt="A cute cat playing with a ball of yarn",
            duration_seconds=5,
            resolution_width=1280,
            resolution_height=720
        )
        
        print(f"📝 Prompt: {request.prompt}")
        print(f"⏱️  Duration: {request.duration_seconds}s")
        print(f"📐 Resolution: {request.resolution_width}x{request.resolution_height}")
        
        try:
            # Start generation
            response = await provider.generate_video(request)
            print(f"\n✅ Generation started!")
            print(f"🆔 Generation ID: {response.generation_id}")
            print(f"📊 Status: {response.status}")
            print(f"⏰ Estimated completion: {response.estimated_completion_time}s")
            
            print(f"\n⏳ You can check status with:")
            print(f"   Generation ID: {response.generation_id}")
            
            return response.generation_id
            
        except Exception as e:
            print(f"❌ Generation failed: {e}")
            return None
    
    # Run the test
    generation_id = asyncio.run(test_generation())
    
    if generation_id:
        print(f"\n🎯 Success! Video generation started with ID: {generation_id}")
        print(f"\n📋 Next steps:")
        print(f"1. Wait for generation to complete (~60-90 seconds)")
        print(f"2. Check status by calling get_status() with the generation ID")
        print(f"3. Download the video when completed")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you've installed the dependencies:")
    print("pip install fal-client httpx")
    
except Exception as e:
    print(f"❌ Error: {e}")