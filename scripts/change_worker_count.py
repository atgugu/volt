#!/usr/bin/env python3
"""
Configuration changer for load balancer worker count.
Easily switch between single and dual instance configurations.

All paths are configurable via environment variables or auto-detected
from the project root.
"""

import os
import sys
import subprocess
import time
from pathlib import Path

# =============================================================================
# Path Configuration (override via environment variables)
# =============================================================================
# Project root: auto-detected as the parent of the scripts/ directory
PROJECT_ROOT = Path(os.getenv(
    "PROJECT_ROOT",
    str(Path(__file__).parent.parent.resolve())
))

# Path to the LLM inference service (contains load_balancer_config.py)
LLM_SERVICE_DIR = PROJECT_ROOT / "services" / "llm_inference"


def show_current_config():
    """Show current configuration."""
    print("Current Configuration:")

    # Add service dir to path so we can import the config
    service_dir = str(LLM_SERVICE_DIR)
    if service_dir not in sys.path:
        sys.path.insert(0, service_dir)
    try:
        import load_balancer_config as config
        config.print_configuration()
    except ImportError:
        print("   Could not load configuration from: " + service_dir)


def change_worker_count(count):
    """Change the worker count and restart services."""
    print(f"\nChanging to {count} worker(s)...")

    # Set environment variable for this session
    if count == 1:
        os.environ["LB_DEPLOYMENT_MODE"] = "single"
        print("   Set deployment mode: SINGLE")
    elif count == 2:
        os.environ["LB_DEPLOYMENT_MODE"] = "dual"
        print("   Set deployment mode: DUAL")
    else:
        os.environ["LB_WORKER_COUNT"] = str(count)
        print(f"   Set worker count: {count}")

    # Show what the new configuration will be
    print("\nNew Configuration Preview:")
    service_dir = str(LLM_SERVICE_DIR)
    if service_dir not in sys.path:
        sys.path.insert(0, service_dir)
    try:
        # Reload the config module to pick up environment changes
        import load_balancer_config
        import importlib
        importlib.reload(load_balancer_config)

        print(f"   Workers: {load_balancer_config.WORKER_COUNT}")
        print(f"   Ports: {load_balancer_config.WORKER_PORTS}")

        # Check VRAM
        vram_check = load_balancer_config.check_vram_availability()
        if vram_check['gpu_detected']:
            print(f"   VRAM Status: {vram_check['recommendation']}")

        # Ask for confirmation
        print(f"\nRestart services with {load_balancer_config.WORKER_COUNT} worker(s)? (y/N): ", end="")

        try:
            response = input().lower().strip()
            if response not in ['y', 'yes']:
                print("Cancelled")
                return False
        except KeyboardInterrupt:
            print("\nCancelled")
            return False

        # Restart services
        print(f"\nRestarting services with {load_balancer_config.WORKER_COUNT} worker(s)...")

        # Pass environment variables to subprocess
        restart_script = PROJECT_ROOT / "scripts" / "restart_services.py"
        env = os.environ.copy()
        result = subprocess.run([
            sys.executable, str(restart_script)
        ], env=env, cwd=str(PROJECT_ROOT))

        if result.returncode == 0:
            print(f"Successfully switched to {load_balancer_config.WORKER_COUNT} worker(s)")
            return True
        else:
            print("Failed to restart services")
            return False

    except Exception as e:
        print(f"Error: {e}")
        return False


def show_options():
    """Show available options."""
    print("Load Balancer Configuration Manager")
    print("=" * 45)
    print("Available commands:")
    print("  1 - Switch to single worker (saves VRAM)")
    print("  2 - Switch to dual workers (load balancing)")
    print("  s - Show current configuration")
    print("  q - Quit")


def main():
    """Main interactive loop."""
    while True:
        show_options()

        try:
            choice = input("\nEnter your choice: ").lower().strip()

            if choice == 'q':
                print("Goodbye!")
                break
            elif choice == 's':
                show_current_config()
            elif choice == '1':
                change_worker_count(1)
            elif choice == '2':
                change_worker_count(2)
            else:
                print("Invalid choice, please try again")

            if choice in ['1', '2']:
                # Pause before showing menu again
                input("\nPress Enter to continue...")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break


if __name__ == "__main__":
    main()
