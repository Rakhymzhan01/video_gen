#!/usr/bin/env python3
"""
Direct test of fal.ai API without internal dependencies
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
    exit(1)

print(f"✅ FAL_KEY found: {fal_key[:10]}...")

try:
    import fal_client
    print("✅ fal_client import successful")
    
    # Configure fal client
    fal_client.api_key = fal_key
    
    async def test_kling_generation():
        """Test Kling video generation directly"""
        print("\n🎬 Testing Kling video generation...")
        
        # Kling 2.1 Master Text-to-Video endpoint
        model_endpoint = "fal-ai/kling-video/v2.1/master/text-to-video"
        
        payload = {
            "prompt": "A cute cat playing with a ball of yarn in slow motion",
            "duration": 5,
            "resolution": "720p",
            "aspect_ratio": "16:9"
        }
        
        print(f"📝 Prompt: {payload['prompt']}")
        print(f"⏱️  Duration: {payload['duration']}s")
        print(f"📐 Resolution: {payload['resolution']}")
        print(f"🖼️  Aspect ratio: {payload['aspect_ratio']}")
        print(f"🔗 Model: {model_endpoint}")
        
        try:
            print("\n🚀 Submitting to fal.ai...")
            
            # Submit to fal.ai queue
            handler = await fal_client.submit(
                model_endpoint,
                arguments=payload
            )
            
            request_id = handler.request_id
            print(f"✅ Generation started!")
            print(f"🆔 Request ID: {request_id}")
            
            print(f"\n⏳ Checking initial status...")
            status = await fal_client.status(request_id)
            print(f"📊 Status: {status.status}")
            
            if status.status == "IN_PROGRESS":
                print(f"🔄 Video is being generated...")
                print(f"⏰ This usually takes 60-90 seconds")
                print(f"\n💡 You can check status later with:")
                print(f"   Request ID: {request_id}")
                
                # Wait a bit and check again
                print(f"\n⏳ Waiting 30 seconds before checking again...")
                await asyncio.sleep(30)
                
                status = await fal_client.status(request_id)
                print(f"📊 Updated status: {status.status}")
                
                if status.status == "COMPLETED":
                    print(f"🎉 Video generation completed!")
                    result = status.result
                    if hasattr(result, 'video') and hasattr(result.video, 'url'):
                        video_url = result.video.url
                        print(f"🎬 Video URL: {video_url}")
                    elif isinstance(result, dict) and 'video' in result:
                        video_url = result['video'].get('url')
                        print(f"🎬 Video URL: {video_url}")
                    else:
                        print(f"📄 Result: {result}")
                elif status.status == "IN_PROGRESS":
                    print(f"⏳ Still processing... Check again in a few minutes")
                else:
                    print(f"❓ Status: {status.status}")
            
            return request_id
            
        except Exception as e:
            print(f"❌ Generation failed: {e}")
            print(f"🔍 Error type: {type(e)}")
            return None
    
    # Run the test
    print("🚀 Starting fal.ai video generation test...\n")
    generation_id = asyncio.run(test_kling_generation())
    
    if generation_id:
        print(f"\n🎯 Test completed! Generation ID: {generation_id}")
        print(f"\n📋 What happened:")
        print(f"✅ Successfully connected to fal.ai")
        print(f"✅ Submitted video generation request")
        print(f"✅ Received generation ID")
        print(f"✅ Checked initial status")
        print(f"\n🔥 Your fal.ai providers are working!")
    else:
        print(f"\n❌ Test failed - check the error messages above")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you've installed fal-client:")
    print("python -m pip install fal-client --break-system-packages")
    
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    print(f"🔍 Error type: {type(e)}")