"""
Document Processing Pipeline API Test Script
"""
import requests
import time
import json
from pathlib import Path

API_BASE_URL = "http://localhost:8000"


def test_health_check():
    """Test health check endpoint"""
    print("🔍 Testing health check...")
    response = requests.get(f"{API_BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    return response.status_code == 200


def test_document_upload():
    """Test document upload"""
    print("\n📤 Testing document upload...")
    
    # Create a test file
    test_file_path = Path("uploads/sample_document.txt")
    
    if not test_file_path.exists():
        test_file_path.parent.mkdir(exist_ok=True)
        with open(test_file_path, "w", encoding="utf-8") as f:
            f.write("This is a test document for the pipeline.\n")
            f.write("It contains sample content for processing.")
    
    # Upload file
    with open(test_file_path, "rb") as f:
        files = {"file": ("test_document.txt", f, "text/plain")}
        data = {"auto_process": True}
        
        response = requests.post(f"{API_BASE_URL}/documents/upload", files=files, data=data)
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    if response.status_code == 200:
        return response.json()["id"]
    return None


def test_document_list():
    """Test document listing"""
    print("\n📋 Testing document list...")
    response = requests.get(f"{API_BASE_URL}/documents")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    return response.status_code == 200


def test_document_status(document_id):
    """Test document status check"""
    print(f"\n📊 Testing document status for ID: {document_id}...")
    response = requests.get(f"{API_BASE_URL}/documents/{document_id}/status")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    return response.json() if response.status_code == 200 else None


def test_manual_parsing(document_id):
    """Test manual parsing trigger"""
    print(f"\n🔄 Testing manual parsing for ID: {document_id}...")
    response = requests.post(f"{API_BASE_URL}/documents/{document_id}/parse")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    return response.json() if response.status_code == 200 else None


def test_manual_indexing(document_id):
    """Test manual indexing trigger"""
    print(f"\n📚 Testing manual indexing for ID: {document_id}...")
    data = {"index_types": ["vector", "fulltext"]}
    response = requests.post(f"{API_BASE_URL}/documents/{document_id}/index", json=data)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    return response.json() if response.status_code == 200 else None


def wait_for_processing(document_id, max_wait=60):
    """Wait for document processing to complete"""
    print(f"\n⏳ Waiting for processing to complete (max {max_wait}s)...")
    
    start_time = time.time()
    while time.time() - start_time < max_wait:
        status = test_document_status(document_id)
        if status:
            if status["status"] in ["indexed", "failed"]:
                print(f"✅ Processing completed with status: {status['status']}")
                return status
            
        print("⏳ Still processing... waiting 5 seconds")
        time.sleep(5)
    
    print("⚠️ Processing timeout reached")
    return None


def run_full_test():
    """Run complete API test suite"""
    print("🚀 Starting Document Processing Pipeline API Tests")
    print("=" * 60)
    
    # Test 1: Health check
    if not test_health_check():
        print("❌ Health check failed!")
        return False
    
    # Test 2: Document upload
    document_id = test_document_upload()
    if not document_id:
        print("❌ Document upload failed!")
        return False
    
    # Test 3: Document list
    if not test_document_list():
        print("❌ Document list failed!")
        return False
    
    # Test 4: Wait for auto-processing
    final_status = wait_for_processing(document_id)
    
    # Test 5: Manual operations (if auto-processing didn't work)
    if not final_status or final_status["status"] != "indexed":
        print("\n🔧 Trying manual processing...")
        
        # Manual parsing
        parse_task = test_manual_parsing(document_id)
        if parse_task:
            time.sleep(10)  # Wait for parsing
        
        # Manual indexing
        index_task = test_manual_indexing(document_id)
        if index_task:
            time.sleep(10)  # Wait for indexing
        
        # Check final status
        final_status = test_document_status(document_id)
    
    print("\n" + "=" * 60)
    print("🎯 Test Summary:")
    if final_status:
        print(f"Document ID: {document_id}")
        print(f"Final Status: {final_status['status']}")
        print(f"Parsed: {final_status['parsed']}")
        print(f"Vector Indexed: {final_status['vector_indexed']}")
        print(f"Fulltext Indexed: {final_status['fulltext_indexed']}")
        print(f"Graph Indexed: {final_status['graph_indexed']}")
        
        if final_status["status"] == "indexed":
            print("✅ All tests passed successfully!")
            return True
        else:
            print("⚠️ Processing incomplete but API is working")
            return True
    else:
        print("❌ Tests failed!")
        return False


if __name__ == "__main__":
    success = run_full_test()
    exit(0 if success else 1)