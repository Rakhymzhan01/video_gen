#!/usr/bin/env python3
"""
Test script for fal.ai providers (Kling, SeedDance, Wan)
"""
import asyncio
import os
import sys
sys.path.append('.')

from shared.providers.factory import ProviderFactory
from shared.providers.base import VideoGenerationRequest


async def test_provider_creation():
    """Test that we can create provider instances."""
    print("🧪 Testing provider creation...")
    
    providers = ["kling", "seedance", "wan_fal"]
    
    for provider_name in providers:
        try:
            provider = ProviderFactory.create_provider(provider_name)
            print(f"✅ {provider_name}: Created successfully")
            
            # Test capabilities
            capabilities = provider.get_capabilities()
            print(f"   - Max duration: {capabilities['max_duration_seconds']}s")
            print(f"   - Max resolution: {capabilities['max_resolution']}")
            print(f"   - Features: {capabilities['features'][:3]}...")
            
        except Exception as e:
            print(f"❌ {provider_name}: Failed to create - {e}")


async def test_available_providers():
    """Test getting available providers."""
    print("\n🔍 Testing available providers...")
    
    available = ProviderFactory.get_available_providers()
    
    fal_providers = ["kling", "seedance", "wan_fal"]
    for provider_name in fal_providers:
        if provider_name in available:
            info = available[provider_name]
            status = "✅ Available" if info["available"] else f"❌ Not available - {info.get('error', 'Unknown error')}"
            print(f"   {provider_name}: {status}")
        else:
            print(f"   {provider_name}: ❌ Not found in registry")


async def test_video_generation_request():
    """Test creating a video generation request."""
    print("\n🎬 Testing video generation request...")
    
    if not os.getenv("FAL_KEY"):
        print("❌ FAL_KEY not set in environment. Skipping generation test.")
        return
    
    try:
        # Create a simple text-to-video request
        request = VideoGenerationRequest(
            prompt="A cute cat playing with a ball of yarn in slow motion",
            duration_seconds=5,
            resolution_width=1280,
            resolution_height=720,
            fps=24
        )
        
        # Test with Kling provider
        provider = ProviderFactory.create_provider("kling")
        print(f"✅ Created request: {request.prompt[:50]}...")
        print(f"   Duration: {request.duration_seconds}s, Resolution: {request.resolution_width}x{request.resolution_height}")
        
        # Validate the request
        is_valid = provider.validate_request(request)
        print(f"   Validation: {'✅ Valid' if is_valid else '❌ Invalid'}")
        
        # Calculate estimated cost
        estimated_cost = provider.calculate_cost(request)
        print(f"   Estimated cost: ${estimated_cost:.2f}")
        
        print("\n⚠️  To test actual generation, uncomment the generation code below and add your FAL_KEY")
        
        # Uncomment to test actual generation (requires valid FAL_KEY)
        # response = await provider.generate_video(request)
        # print(f"   Generation started: {response.generation_id}")
        # print(f"   Status: {response.status}")
        # print(f"   Estimated completion: {response.estimated_completion_time}s")
        
    except Exception as e:
        print(f"❌ Request test failed: {e}")


async def main():
    """Run all tests."""
    print("🚀 Testing fal.ai providers implementation\n")
    
    await test_provider_creation()
    await test_available_providers()
    await test_video_generation_request()
    
    print("\n✅ All tests completed!")
    print("\n📋 Next steps:")
    print("1. Add your FAL_KEY to the .env file")
    print("2. Uncomment the generation code in test_video_generation_request()")
    print("3. Run this script again to test actual video generation")


if __name__ == "__main__":
    asyncio.run(main())