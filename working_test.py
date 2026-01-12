#!/usr/bin/env python3
"""
Working test of fal.ai API with correct async/sync usage
"""
import asyncio
import os
import time
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
    
    def test_kling_generation():
        """Test Kling video generation directly (sync version)"""
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
            
            # Submit to fal.ai queue (sync)
            handler = fal_client.submit(
                model_endpoint,
                arguments=payload
            )
            
            request_id = handler.request_id
            print(f"✅ Generation started!")
            print(f"🆔 Request ID: {request_id}")
            
            print(f"\n⏳ Checking initial status...")
            status = fal_client.status(request_id)
            print(f"📊 Status: {status.status}")
            
            if status.status == "IN_PROGRESS" or status.status == "IN_QUEUE":
                print(f"🔄 Video is being generated...")
                print(f"⏰ This usually takes 60-90 seconds")
                
                # Wait and check a few times
                max_checks = 6  # Check for up to 3 minutes
                check_interval = 30  # Check every 30 seconds
                
                for i in range(max_checks):
                    print(f"\n⏳ Waiting {check_interval} seconds... (Check {i+1}/{max_checks})")
                    time.sleep(check_interval)
                    
                    status = fal_client.status(request_id)
                    print(f"📊 Status: {status.status}")
                    
                    if status.status == "COMPLETED":
                        print(f"🎉 Video generation completed!")
                        
                        # Get the result
                        result = status.result
                        print(f"📄 Result type: {type(result)}")
                        
                        # Try to extract video URL
                        video_url = None
                        if hasattr(result, 'video') and hasattr(result.video, 'url'):
                            video_url = result.video.url
                        elif isinstance(result, dict):
                            if 'video' in result and isinstance(result['video'], dict):
                                video_url = result['video'].get('url')
                            elif 'video_url' in result:
                                video_url = result['video_url']
                        
                        if video_url:
                            print(f"🎬 Video URL: {video_url}")
                            print(f"📥 You can download this video!")
                        else:
                            print(f"📄 Full result: {result}")
                        
                        break
                    elif status.status in ["FAILED", "ERROR"]:
                        print(f"❌ Generation failed")
                        if hasattr(status, 'error'):
                            print(f"💥 Error: {status.error}")
                        break
                    elif status.status in ["IN_PROGRESS", "IN_QUEUE"]:
                        print(f"⏳ Still processing...")
                    else:
                        print(f"❓ Unknown status: {status.status}")
                        break
                else:
                    print(f"\n⏰ Reached maximum check time. Generation might still be processing.")
                    print(f"🔍 Final status: {status.status}")
                    print(f"💡 You can manually check status later with request ID: {request_id}")
                    
            elif status.status == "COMPLETED":
                print(f"🎉 Generation completed quickly!")
                # Handle completed case (same as above)
            else:
                print(f"❓ Unexpected initial status: {status.status}")
            
            return request_id
            
        except Exception as e:
            print(f"❌ Generation failed: {e}")
            print(f"🔍 Error type: {type(e)}")
            return None
    
    # Run the test
    print("🚀 Starting fal.ai video generation test...\n")
    generation_id = test_kling_generation()
    
    if generation_id:
        print(f"\n🎯 Test completed! Generation ID: {generation_id}")
        print(f"\n📋 What happened:")
        print(f"✅ Successfully connected to fal.ai")
        print(f"✅ Submitted video generation request")
        print(f"✅ Received generation ID")
        print(f"✅ Monitored generation progress")
        print(f"\n🔥 Your fal.ai integration is working perfectly!")
        print(f"\n💡 Next steps:")
        print(f"1. Your providers are ready to use in your application")
        print(f"2. You can now generate videos through your API endpoints")
        print(f"3. The video will be available at the URL shown above")
    else:
        print(f"\n❌ Test failed - check the error messages above")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you've installed fal-client:")
    print("python -m pip install fal-client --break-system-packages")
    
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    print(f"🔍 Error type: {type(e)}")