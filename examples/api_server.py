#!/usr/bin/env python3
"""Example: Running the nomon Camera REST API Server

This script demonstrates how to start the REST API server
and make requests to control the camera remotely.

Requirements:
    pip install nomon[api]
"""

import time
from pathlib import Path

# ============================================================================
# Example 1: Start API server locally (HTTPS)
# ============================================================================

if __name__ == "__main__":
    from nomon.api import APIServer

    # Initialize API server on localhost with HTTPS
    # Self-signed certificates are automatically created in .certs/
    server = APIServer(
        host="127.0.0.1",  # Local network only
        port=8443,  # HTTPS default port
        use_ssl=True,  # Enable TLS encryption
    )

    print("=" * 70)
    print("nomon Camera REST API Server")
    print("=" * 70)
    print()
    print("Server starting at:")
    print("  HTTPS: https://127.0.0.1:8443")
    print()
    print("API Documentation:")
    print("  Interactive Docs: https://127.0.0.1:8443/docs")
    print("  ReDoc: https://127.0.0.1:8443/redoc")
    print()
    print("Endpoints:")
    print("  GET  /api/camera/status        - Get camera status")
    print("  POST /api/camera/capture       - Capture still image")
    print("  POST /api/camera/record/start  - Start video recording")
    print("  POST /api/camera/record/stop   - Stop video recording")
    print()
    print("TLS Certificates (auto-generated):")
    print(f"  Cert: {server.cert_file}")
    print(f"  Key:  {server.key_file}")
    print()
    print("Note: Use --insecure flag or ignore certificate warnings in")
    print("client tools when connecting to self-signed certificates.")
    print()
    print("=" * 70)
    print()
    print("Press Ctrl+C to stop the server")
    print()

    # Start the server (blocking call)
    server.run()


# ============================================================================
# Example 2: Background server (for integration tests or multi-threaded apps)
# ============================================================================

if False:  # Change to True to run this example
    from nomon.api import APIServer
    import time
    import sys

    # Create server that listens on all network interfaces
    server = APIServer(
        host="0.0.0.0",  # Listen on all interfaces
        port=8443,
        use_ssl=True,
    )

    # Start server in background thread
    thread = server.start_background()
    print("Server is running in background")

    # Server is now ready for requests
    # You can make HTTP requests to https://localhost:8443
    print("Server started. Sleeping for 10 seconds...")
    time.sleep(10)

    print("Server thread is alive:", thread.is_alive())
    sys.exit(0)


# ============================================================================
# Example 3: Making requests to the API with curl
# ============================================================================

"""
Once the server is running, you can make requests from another terminal:

# Check server health
curl -k https://localhost:8443/

# Get camera status  
curl -k https://localhost:8443/api/camera/status

# Capture a still image
curl -k -X POST https://localhost:8443/api/camera/capture \
  -H "Content-Type: application/json" \
  -d '{"filename": "photo.jpg"}'

# Start video recording
curl -k -X POST https://localhost:8443/api/camera/record/start \
  -H "Content-Type: application/json" \
  -d '{"filename": "video.mp4", "encoder": "h264"}'

# Stop video recording
curl -k -X POST https://localhost:8443/api/camera/record/stop

# Access interactive API docs
# https://localhost:8443/docs
# https://localhost:8443/redoc

Note: Use -k flag with curl to ignore self-signed certificate warnings.
"""


# ============================================================================
# Example 4: Python client
# ============================================================================

"""
Example client code using the requests library:

    import requests
    import json
    
    BASE_URL = "https://localhost:8443"
    
    # Disable SSL verification for self-signed certs
    # (In production, use proper certificates!)
    session = requests.Session()
    session.verify = False
    
    # Get camera status
    response = session.get(f"{BASE_URL}/api/camera/status")
    status = response.json()
    print(f"Camera: {status['resolution']} @ {status['fps']} fps")
    
    # Capture image
    response = session.post(
        f"{BASE_URL}/api/camera/capture",
        json={"filename": "test.jpg"}
    )
    print(response.json())
    
    # Start recording
    response = session.post(
        f"{BASE_URL}/api/camera/record/start",
        json={"filename": "test.mp4", "encoder":  "h264"}
    )
    print(response.json())
    
    # Wait a bit...
    import time
    time.sleep(5)
    
    # Stop recording
    response = session.post(f"{BASE_URL}/api/camera/record/stop")
    print(response.json())
"""
