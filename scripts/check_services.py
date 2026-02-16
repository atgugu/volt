"""
Service Health Check Utility

Quick health check for all framework services.
"""

import sys
import os
import httpx

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Service endpoints
SERVICES = {
    "Backend": f"http://localhost:{os.getenv('BACKEND_PORT', '10821')}/health",
    "LLM (Load Balancer)": f"http://localhost:{os.getenv('LLM_PORT', '8000')}/health",
    "TTS Service": f"http://localhost:{os.getenv('TTS_PORT', '8033')}/health",
    "STT Service": f"http://localhost:{os.getenv('STT_PORT', '8034')}/health",
}


def check_service(name: str, url: str) -> bool:
    """Check if a service is healthy."""
    try:
        response = httpx.get(url, timeout=5.0)
        if response.status_code == 200:
            print(f"  [OK] {name}: healthy ({url})")
            return True
        else:
            print(f"  [!!] {name}: status {response.status_code} ({url})")
            return False
    except httpx.ConnectError:
        print(f"  [--] {name}: not running ({url})")
        return False
    except Exception as e:
        print(f"  [!!] {name}: error - {e}")
        return False


def main():
    print("\n=== Service Health Check ===\n")

    healthy = 0
    total = len(SERVICES)

    for name, url in SERVICES.items():
        if check_service(name, url):
            healthy += 1

    print(f"\n  {healthy}/{total} services healthy\n")

    # Check load balancer stats if available
    lb_stats_url = f"http://localhost:{os.getenv('LLM_PORT', '8000')}/stats"
    try:
        response = httpx.get(lb_stats_url, timeout=5.0)
        if response.status_code == 200:
            stats = response.json()
            workers = stats.get("workers", [])
            print(f"  Load Balancer: {len(workers)} worker(s)")
            for w in workers:
                print(f"    - {w.get('url', 'unknown')}: {w.get('status', 'unknown')}")
            print()
    except Exception:
        pass

    return 0 if healthy == total else 1


if __name__ == "__main__":
    sys.exit(main())
