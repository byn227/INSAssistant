import json
import time
import requests
from datetime import datetime


class QdrantMonitor:
    def __init__(self, host="localhost", port=6333):
        self.base_url = f"http://{host}:{port}"
    
    def check_health(self):
        """Check if Qdrant is running"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def get_collections(self):
        """Get all collections"""
        try:
            response = requests.get(f"{self.base_url}/collections")
            data = response.json()
            return data.get('result', {}).get('collections', [])
        except:
            return []
    
    def get_collection_info(self, collection_name):
        """Get detailed info about a collection"""
        try:
            response = requests.get(f"{self.base_url}/collections/{collection_name}")
            data = response.json()
            return data.get('result', {})
        except:
            return {}
    
    def print_status(self):
        """Print current status"""
        print("\033[2J\033[H")  # Clear screen
        print("=" * 80)
        print(f"🔍 Qdrant Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        if not self.check_health():
            print("\n Qdrant is not running!")
            print("\nTo start Qdrant:")
            print("  docker run -d -p 6333:6333 -p 6334:6334 \\")
            print("      -v $(pwd)/qdrant_storage:/qdrant/storage:z \\")
            print("      --name qdrant qdrant/qdrant")
            return False
        
        print("\n Qdrant is running")
        print(f"\n Dashboard: {self.base_url}/dashboard")
        
        collections = self.get_collections()
        
        if not collections:
            print("\n No collections yet")
            return True
        
        print(f"\n Collections ({len(collections)}):")
        print("-" * 80)
        
        for coll in collections:
            name = coll.get('name', 'Unknown')
            info = self.get_collection_info(name)
            
            points_count = info.get('points_count', 0)
            vectors_count = info.get('vectors_count', 0)
            
            config = info.get('config', {})
            params = config.get('params', {})
            vectors_config = params.get('vectors', {})
            
            # Get vector size and distance
            if isinstance(vectors_config, dict):
                vector_size = vectors_config.get('size', 'N/A')
                distance = vectors_config.get('distance', 'N/A')
            else:
                vector_size = 'N/A'
                distance = 'N/A'
            
            print(f"\n📂 {name}")
            print(f"   Points:      {points_count:,}")
            print(f"   Vectors:     {vectors_count:,}")
            print(f"   Dimensions:  {vector_size}")
            print(f"   Distance:    {distance}")
            
            # Status
            status = info.get('status', 'unknown')
            if status == 'green':
                status_icon = "🟢"
            elif status == 'yellow':
                status_icon = "🟡"
            else:
                status_icon = "🔴"
            print(f"   Status:      {status_icon} {status}")
        
        print("\n" + "-" * 80)
        print("Press Ctrl+C to exit | Updates every 5 seconds")
        return True
    
    def monitor(self, interval=5):
        """Monitor in real-time"""
        try:
            while True:
                if not self.print_status():
                    print("\nRetrying in 10 seconds...")
                    time.sleep(10)
                else:
                    time.sleep(interval)
        except KeyboardInterrupt:
            print("\n\n👋 Monitoring stopped")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Monitor Qdrant collections")
    parser.add_argument('--host', default='localhost', help='Qdrant host')
    parser.add_argument('--port', type=int, default=6333, help='Qdrant port')
    parser.add_argument('--interval', type=int, default=5, help='Update interval (seconds)')
    parser.add_argument('--once', action='store_true', help='Show status once and exit')
    
    args = parser.parse_args()
    
    monitor = QdrantMonitor(host=args.host, port=args.port)
    
    if args.once:
        monitor.print_status()
    else:
        monitor.monitor(interval=args.interval)


if __name__ == "__main__":
    main()
