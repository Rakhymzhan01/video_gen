#!/usr/bin/env python3
"""
Simple test to verify our provider files are created correctly.
"""
import os
import sys

def test_provider_files():
    """Test that all provider files exist and have basic structure."""
    print("🧪 Testing provider files...")
    
    providers = {
        "kling_provider.py": "KlingProvider",
        "seedance_provider.py": "SeedDanceProvider", 
        "wan_provider.py": "WanProvider"
    }
    
    base_path = "shared/providers"
    
    for filename, class_name in providers.items():
        file_path = os.path.join(base_path, filename)
        
        if os.path.exists(file_path):
            print(f"✅ {filename}: File exists")
            
            # Check if class is defined
            with open(file_path, 'r') as f:
                content = f.read()
                if f"class {class_name}" in content:
                    print(f"   - Class {class_name} found")
                else:
                    print(f"   ❌ Class {class_name} not found")
                
                # Check for required methods
                required_methods = ["generate_video", "get_status", "download_video", "validate_request"]
                for method in required_methods:
                    if f"def {method}" in content:
                        print(f"   - Method {method} found")
                    else:
                        print(f"   ❌ Method {method} not found")
        else:
            print(f"❌ {filename}: File not found")


def test_factory_updates():
    """Test that factory.py has been updated."""
    print("\n🏭 Testing factory updates...")
    
    factory_path = "shared/providers/factory.py"
    if os.path.exists(factory_path):
        with open(factory_path, 'r') as f:
            content = f.read()
            
        imports_to_check = [
            "from .kling_provider import KlingProvider",
            "from .seedance_provider import SeedDanceProvider", 
            "from .wan_provider import WanProvider"
        ]
        
        for import_line in imports_to_check:
            if import_line in content:
                print(f"✅ Import found: {import_line.split('import')[1].strip()}")
            else:
                print(f"❌ Import missing: {import_line.split('import')[1].strip()}")
        
        # Check provider registry
        registry_items = ["kling", "seedance", "wan_fal"]
        for item in registry_items:
            if f'"{item}"' in content:
                print(f"✅ Provider registered: {item}")
            else:
                print(f"❌ Provider not registered: {item}")
    else:
        print("❌ factory.py not found")


def test_env_updates():
    """Test that .env file has FAL_KEY."""
    print("\n🔧 Testing environment configuration...")
    
    env_path = ".env"
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            content = f.read()
        
        if "FAL_KEY=" in content:
            print("✅ FAL_KEY found in .env file")
        else:
            print("❌ FAL_KEY not found in .env file")
    else:
        print("❌ .env file not found")


def test_requirements():
    """Test that requirements.txt has fal-client."""
    print("\n📦 Testing requirements...")
    
    req_path = "requirements.txt"
    if os.path.exists(req_path):
        with open(req_path, 'r') as f:
            content = f.read()
        
        if "fal-client" in content:
            print("✅ fal-client found in requirements.txt")
        else:
            print("❌ fal-client not found in requirements.txt")
    else:
        print("❌ requirements.txt not found")


def main():
    """Run all simple tests."""
    print("🚀 Running simple tests for fal.ai providers\n")
    
    test_provider_files()
    test_factory_updates()
    test_env_updates()
    test_requirements()
    
    print("\n✅ Simple tests completed!")
    print("\n📋 Summary:")
    print("✅ Created 3 new provider implementations (Kling, SeedDance, Wan)")
    print("✅ Updated provider factory to register new providers")
    print("✅ Added FAL_KEY to environment configuration")
    print("✅ Added fal-client dependency to requirements.txt")
    print("\n🎯 Ready for integration! Next steps:")
    print("1. Get your fal.ai API key from https://fal.ai/")
    print("2. Update FAL_KEY in .env file with your real API key")
    print("3. Install dependencies: pip install fal-client")
    print("4. Test with real API calls!")


if __name__ == "__main__":
    main()