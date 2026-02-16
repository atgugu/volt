#!/usr/bin/env python3
"""
Service Management Script
Cleanly stops and restarts all services (Backend, TTS, STT).

All paths are configurable via environment variables or auto-detected
from the project root.
"""

import subprocess
import time
import sys
import os
import requests
from pathlib import Path

# =============================================================================
# Path Configuration (override via environment variables)
# =============================================================================
# Project root: auto-detected as the parent of the scripts/ directory
PROJECT_ROOT = Path(os.getenv(
    "PROJECT_ROOT",
    str(Path(__file__).parent.parent.resolve())
))

# Virtual environment path (set VENV_PATH to override)
VENV_PATH = Path(os.getenv("VENV_PATH", str(PROJECT_ROOT / "venv")))
PYTHON_BIN = VENV_PATH / "bin" / "python"

# Service directories (relative to PROJECT_ROOT)
BACKEND_DIR = PROJECT_ROOT / "backend"
TTS_SERVICE_DIR = PROJECT_ROOT / "services" / "tts_service"
STT_SERVICE_DIR = PROJECT_ROOT / "services" / "stt_service"

# Service ports (override via environment variables)
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "10821"))
TTS_PORT = int(os.getenv("TTS_PORT", "8033"))
STT_PORT = int(os.getenv("STT_PORT", "8034"))


def check_virtual_environment():
    """Check if the virtual environment exists and is properly configured."""
    python_path = VENV_PATH / "bin" / "python"
    activate_path = VENV_PATH / "bin" / "activate"

    if not VENV_PATH.exists():
        print(f"Virtual environment not found at {VENV_PATH}")
        return False

    if not python_path.exists():
        print("Python executable not found in virtual environment")
        return False

    if not activate_path.exists():
        print("Activation script not found in virtual environment")
        return False

    print("Virtual environment verified")
    return True


def manage_service_logs(clean_old=True):
    """Manage service log files."""
    log_files = [
        BACKEND_DIR / "backend_service.log",
        TTS_SERVICE_DIR / "tts_service.log",
        STT_SERVICE_DIR / "stt_service.log",
    ]

    print("\nManaging service logs...")

    for log_file in log_files:
        if log_file.exists():
            if clean_old:
                # Backup old log with timestamp
                import datetime

                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = log_file.with_suffix(f".{timestamp}.log")
                try:
                    log_file.rename(backup_path)
                    print(f"   Backed up {log_file.name} to {backup_path.name}")
                except Exception as e:
                    print(f"   Warning: Could not backup {log_file.name}: {e}")
                    # If backup fails, just truncate the file
                    try:
                        log_file.write_text("")
                        print(f"   Cleared {log_file.name}")
                    except Exception as e2:
                        print(f"   Warning: Could not clear {log_file.name}: {e2}")
            else:
                print(f"   Keeping existing {log_file.name}")
        else:
            print(f"   {log_file.name} does not exist (will be created)")

        # Ensure parent directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)


def run_command(cmd, description="", check=True, verbose=False):
    """Run a command and handle errors."""
    if verbose and description:
        print(f"   {description}")
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, check=check
        )
        if verbose and result.stdout.strip():
            print(f"   {result.stdout.strip()}")
        return result
    except subprocess.CalledProcessError as e:
        if verbose:
            print(f"   Error: {e}")
            if e.stderr:
                print(f"   {e.stderr.strip()}")
        return e


def kill_service_processes():
    """Kill all running service processes with verification."""
    print("\nStopping all services...")

    # Patterns to catch all service processes
    project_root_str = str(PROJECT_ROOT)
    patterns = [
        f"PYTHONPATH.*{project_root_str}.*python.*backend",
        f"{project_root_str}.*python.*backend",
        "tts_service.*main.py",
        "stt_service.*main.py",
        "services/tts_service",
        "services/stt_service",
    ]

    # First attempt: graceful shutdown
    for pattern in patterns:
        run_command(f"pkill -f '{pattern}'", check=False)

    # Also kill any processes holding our ports specifically
    ports_to_kill = [BACKEND_PORT, TTS_PORT, STT_PORT]
    _force_kill_port_users(ports_to_kill)

    # Wait and verify processes are actually dead
    max_wait_time = 15
    shown_waiting = False
    for i in range(max_wait_time):
        remaining_processes = []
        for pattern in patterns:
            result = run_command(f"pgrep -f '{pattern}'", check=False)
            if result.returncode == 0 and result.stdout.strip():
                remaining_processes.extend(result.stdout.strip().split("\n"))

        if not remaining_processes:
            break

        if not shown_waiting:
            print("   Waiting for processes to terminate...")
            shown_waiting = True
        time.sleep(1)
    else:
        # Force kill remaining processes
        for pattern in patterns:
            run_command(f"pkill -9 -f '{pattern}'", check=False)

        # Additional force kill for any python processes in our directories
        run_command(f"pkill -9 -f '{project_root_str}.*python'", check=False)

        # Final verification
        time.sleep(2)

    # Clean up zombie/defunct processes
    run_command("kill -CHLD $$", check=False)

    # Verify ports are actually free
    _verify_ports_free()
    print("All services stopped")


def _force_kill_port_users(ports):
    """Force kill any processes using the specified ports."""
    for port in ports:
        result = run_command(
            f"netstat -tlnp 2>/dev/null | grep ':{port}' || ss -tlnp | grep ':{port}'",
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split("\n")
            for line in lines:
                if f":{port}" in line:
                    try:
                        # Extract PID from netstat/ss output
                        parts = line.split()
                        for part in parts:
                            if "/" in part and part.split("/")[0].isdigit():
                                pid = part.split("/")[0]
                                run_command(f"kill -9 {pid}", check=False)
                                break
                    except (IndexError, ValueError):
                        continue


def _verify_ports_free():
    """Verify that required ports are actually free."""
    ports_to_check = [BACKEND_PORT, TTS_PORT, STT_PORT]

    for port in ports_to_check:
        result = run_command(
            f"netstat -tlnp 2>/dev/null | grep ':{port}' || ss -tlnp | grep ':{port}'",
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Final attempt to kill the process using this port
            lines = result.stdout.strip().split("\n")
            for line in lines:
                if f":{port}" in line:
                    try:
                        # Extract PID from netstat/ss output
                        parts = line.split()
                        for part in parts:
                            if "/" in part and part.split("/")[0].isdigit():
                                pid = part.split("/")[0]
                                run_command(f"kill -9 {pid}", check=False)
                                break
                    except (IndexError, ValueError):
                        continue


def _wait_for_port_free(port, timeout=10):
    """Wait for a port to become free."""
    for i in range(timeout):
        result = run_command(
            f"netstat -tlnp 2>/dev/null | grep ':{port}' || ss -tlnp | grep ':{port}'",
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return True  # Port is free
        time.sleep(1)
    return False  # Port still in use after timeout


def check_service_health(url, service_name, timeout=5):
    """Check if a service is healthy."""
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            print(f"   {service_name} is healthy")
            return True
        else:
            print(f"   {service_name} returned status {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"   {service_name} is not responding: {e}")
        return False


def start_backend_service():
    """Start the backend service."""
    print(f"\nStarting backend service on port {BACKEND_PORT}...")

    if not BACKEND_DIR.exists():
        print(f"   Backend directory not found: {BACKEND_DIR}")
        return False

    # Verify port is actually free before starting
    if not _wait_for_port_free(BACKEND_PORT, timeout=5):
        print(f"   Port {BACKEND_PORT} is still in use, cannot start backend service")
        return False

    # Start backend service in background with explicit Python path and proper PYTHONPATH
    cmd = (
        f"cd {PROJECT_ROOT} && "
        f"PYTHONPATH={PROJECT_ROOT} "
        f"nohup {PYTHON_BIN} backend/app.py "
        f"> backend/backend_service.log 2>&1 &"
    )
    run_command(cmd, verbose=True)

    # Wait for service to start
    print("   Waiting for backend service to initialize...")
    shown_waiting = False
    for i in range(60):
        time.sleep(1)

        if check_service_health(
            f"http://localhost:{BACKEND_PORT}/health", "Backend service"
        ):
            return True

        if i > 10 and i % 20 == 0 and not shown_waiting:
            print(f"   Initializing... ({i}/60 seconds)")
            shown_waiting = True

    print("   Backend service failed to start within 60 seconds")
    log_file = BACKEND_DIR / "backend_service.log"
    print(f"   Check log file: {log_file}")

    # Try to show the last few lines of the log for debugging
    try:
        if log_file.exists():
            print("   Last few log lines:")
            run_command(f"tail -n 5 {log_file}", check=False, verbose=True)
    except Exception:
        pass

    return False


def start_tts_service():
    """Start the TTS (Text-to-Speech) service."""
    print(f"\nStarting TTS service on port {TTS_PORT}...")

    if not TTS_SERVICE_DIR.exists():
        print(f"   TTS service directory not found: {TTS_SERVICE_DIR}")
        return False

    # Verify port is actually free before starting
    if not _wait_for_port_free(TTS_PORT, timeout=5):
        print(f"   Port {TTS_PORT} is still in use, cannot start TTS service")
        return False

    # Start TTS service in background
    cmd = (
        f"cd {TTS_SERVICE_DIR} && "
        f"nohup {PYTHON_BIN} main.py "
        f"> tts_service.log 2>&1 &"
    )
    run_command(cmd, verbose=True)

    # Wait for service to start
    print("   Waiting for TTS service to initialize...")
    for i in range(30):
        time.sleep(1)

        if check_service_health(
            f"http://localhost:{TTS_PORT}/health", "TTS service"
        ):
            return True

        if i > 5 and i % 10 == 0:
            print(f"   Initializing... ({i}/30 seconds)")

    print("   TTS service failed to start within 30 seconds")
    log_file = TTS_SERVICE_DIR / "tts_service.log"
    print(f"   Check log file: {log_file}")

    # Try to show the last few lines of the log for debugging
    try:
        if log_file.exists():
            print("   Last few log lines:")
            run_command(f"tail -n 5 {log_file}", check=False, verbose=True)
    except Exception:
        pass

    return False


def start_stt_service():
    """Start the STT (Speech-to-Text) service."""
    print(f"\nStarting STT service on port {STT_PORT}...")

    if not STT_SERVICE_DIR.exists():
        print(f"   STT service directory not found: {STT_SERVICE_DIR}")
        return False

    # Verify port is actually free before starting
    if not _wait_for_port_free(STT_PORT, timeout=5):
        print(f"   Port {STT_PORT} is still in use, cannot start STT service")
        return False

    # Start STT service in background
    cmd = (
        f"cd {STT_SERVICE_DIR} && "
        f"nohup {PYTHON_BIN} main.py "
        f"> stt_service.log 2>&1 &"
    )
    run_command(cmd, verbose=True)

    # Wait for service to start
    print("   Waiting for STT service to initialize...")
    for i in range(30):
        time.sleep(1)

        if check_service_health(
            f"http://localhost:{STT_PORT}/health", "STT service"
        ):
            return True

        if i > 5 and i % 10 == 0:
            print(f"   Initializing... ({i}/30 seconds)")

    print("   STT service failed to start within 30 seconds")
    log_file = STT_SERVICE_DIR / "stt_service.log"
    print(f"   Check log file: {log_file}")

    # Try to show the last few lines of the log for debugging
    try:
        if log_file.exists():
            print("   Last few log lines:")
            run_command(f"tail -n 5 {log_file}", check=False, verbose=True)
    except Exception:
        pass

    return False


def show_service_status():
    """Show the status of all services."""
    print("\nService Status:")
    print("=" * 50)

    # Check all services
    check_service_health(
        f"http://localhost:{BACKEND_PORT}/health",
        f"Backend Service (port {BACKEND_PORT})",
    )
    check_service_health(
        f"http://localhost:{TTS_PORT}/health",
        f"TTS Service (port {TTS_PORT})",
    )
    check_service_health(
        f"http://localhost:{STT_PORT}/health",
        f"STT Service (port {STT_PORT})",
    )

    # Show running processes
    print("\nRunning service processes:")
    result = run_command(
        "ps aux | grep -E '(app\\.py|tts_service.*main|stt_service.*main)' | grep -v grep",
        check=False,
        verbose=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        print("   No service processes found")

    # Show port usage
    print("\nPort Status:")
    ports_to_display = [
        (str(BACKEND_PORT), "Backend"),
        (str(TTS_PORT), "TTS"),
        (str(STT_PORT), "STT"),
    ]
    for port, service_name in ports_to_display:
        result = run_command(
            f"netstat -tlnp 2>/dev/null | grep ':{port}' || ss -tlnp | grep ':{port}'",
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            print(f"   Port {port} ({service_name}): IN USE")
        else:
            print(f"   Port {port} ({service_name}): FREE")


def main():
    """Main script execution."""
    print("Service Manager (Backend, TTS, STT)")
    print("=" * 50)
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Venv path:    {VENV_PATH}")

    try:
        # First verify virtual environment exists
        print("\nChecking prerequisites...")
        if not check_virtual_environment():
            print(
                f"\nVirtual environment verification failed. "
                f"Please ensure {VENV_PATH} exists and is properly configured."
            )
            print("Set VENV_PATH environment variable to override the default path.")
            sys.exit(1)

        # Manage log files (backup old ones)
        manage_service_logs(clean_old=True)

        # Stop all services
        kill_service_processes()

        # Start all services
        services_started = []
        services_failed = []

        # Start TTS service first (needed by backend)
        if start_tts_service():
            services_started.append("TTS")
        else:
            services_failed.append("TTS")
            print("   TTS service failed to start, continuing with other services...")

        # Start STT service
        if start_stt_service():
            services_started.append("STT")
        else:
            services_failed.append("STT")
            print("   STT service failed to start, continuing with other services...")

        # Start backend service
        if start_backend_service():
            services_started.append("Backend")
        else:
            services_failed.append("Backend")
            print("   Backend service failed to start.")

        # Show final status
        show_service_status()

        # Summary
        if services_started:
            print(f"\nSuccessfully started: {', '.join(services_started)}")
        if services_failed:
            print(f"\nFailed to start: {', '.join(services_failed)}")

        if not services_failed:
            print("\nAll services restarted successfully!")

        print("\nService logs:")
        print(f"   Backend: {BACKEND_DIR / 'backend_service.log'}")
        print(f"   TTS:     {TTS_SERVICE_DIR / 'tts_service.log'}")
        print(f"   STT:     {STT_SERVICE_DIR / 'stt_service.log'}")

    except KeyboardInterrupt:
        print("\n\nScript interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
