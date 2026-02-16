"""
Load Balancer Configuration

This configuration file controls how many LLM worker instances to run
and other load balancing settings.
"""

import logging
import os
import subprocess
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# --- Worker Configuration ---
# Number of LLM worker instances to run
# Set to 1 for single instance, 2 for load balancing
# Can be overridden by environment variable LB_WORKER_COUNT
DEFAULT_WORKER_COUNT = 1  # Single worker with high context
WORKER_COUNT = int(os.getenv("LB_WORKER_COUNT", DEFAULT_WORKER_COUNT))

# Base port for worker instances
# Workers will use ports: BASE_PORT, BASE_PORT+1, BASE_PORT+2, etc.
WORKER_BASE_PORT = int(os.getenv("LB_WORKER_BASE_PORT", 8010))

# Generate worker port list based on count
WORKER_PORTS = list(range(WORKER_BASE_PORT, WORKER_BASE_PORT + WORKER_COUNT))

# --- Context Window Configuration ---
# Define different context sizes for intelligent routing
CONTEXT_STANDARD = int(os.getenv("LB_CONTEXT_STANDARD", 3072))  # Standard context for regular queries
CONTEXT_LARGE = int(os.getenv("LB_CONTEXT_LARGE", 8192))        # Large context for complex extraction

# Worker context configuration
# Maps worker port to context configuration
# Default config module name for workers
DEFAULT_CONFIG_MODULE = os.getenv("LB_DEFAULT_CONFIG_MODULE", "config")
LARGE_CONFIG_MODULE = os.getenv("LB_LARGE_CONFIG_MODULE", "config")

WORKER_CONTEXT_CONFIG = {
    WORKER_BASE_PORT: {"context_size": CONTEXT_LARGE, "config_module": LARGE_CONFIG_MODULE},
    WORKER_BASE_PORT + 1: {"context_size": CONTEXT_LARGE, "config_module": LARGE_CONFIG_MODULE},
}

# Prompt length threshold for routing to large context worker
# Prompts longer than this (in characters) will prefer the large context worker
LARGE_CONTEXT_THRESHOLD = int(os.getenv("LB_LARGE_CONTEXT_THRESHOLD", 2500))

# --- Load Balancer Configuration ---
# Port for the load balancer itself (what backend connects to)
LOAD_BALANCER_PORT = int(os.getenv("LB_PORT", 8000))

# Host for all services
LOAD_BALANCER_HOST = os.getenv("LB_HOST", "localhost")

# --- Health Monitoring Configuration ---
# How often to check worker health (seconds)
HEALTH_CHECK_INTERVAL = int(os.getenv("LB_HEALTH_CHECK_INTERVAL", 30))

# Timeout for health checks (seconds)
HEALTH_CHECK_TIMEOUT = int(os.getenv("LB_HEALTH_CHECK_TIMEOUT", 5))

# Request timeout for forwarding requests (seconds)
REQUEST_TIMEOUT = int(os.getenv("LB_REQUEST_TIMEOUT", 300))  # 5 minutes for LLM generation

# Maximum retries before giving up
MAX_RETRIES = int(os.getenv("LB_MAX_RETRIES", 2))

# --- Resource Limits ---
# Estimated VRAM usage per worker (GB) - used for validation
VRAM_PER_WORKER_GB = int(os.getenv("LB_VRAM_PER_WORKER_GB", 14))

# Minimum free VRAM to maintain (GB)
MIN_FREE_VRAM_GB = int(os.getenv("LB_MIN_FREE_VRAM_GB", 5))

# --- Logging Configuration ---
# Log level for the load balancer
LOG_LEVEL = os.getenv("LB_LOG_LEVEL", "INFO")

# Enable verbose worker statistics logging
VERBOSE_STATS = os.getenv("LB_VERBOSE_STATS", "false").lower() == "true"

# --- Advanced Configuration ---
# Load balancing algorithm: "round_robin", "least_connections" (future)
LOAD_BALANCE_ALGORITHM = "round_robin"

# Enable request caching at load balancer level (future feature)
ENABLE_REQUEST_CACHE = False


# --- VRAM Monitoring Functions ---
def get_gpu_memory_info() -> Optional[Dict[str, int]]:
    """
    Get current GPU memory usage information.

    Returns:
        Dictionary with 'used', 'free', 'total' memory in MB, or None if no GPU
    """
    try:
        result = subprocess.run([
            "nvidia-smi", "--query-gpu=memory.used,memory.free,memory.total",
            "--format=csv,noheader,nounits"
        ], capture_output=True, text=True, timeout=10)

        if result.returncode == 0:
            line = result.stdout.strip()
            if line:
                used, free, total = map(int, line.split(', '))
                return {
                    'used_mb': used,
                    'free_mb': free,
                    'total_mb': total,
                    'used_gb': used / 1024,
                    'free_gb': free / 1024,
                    'total_gb': total / 1024
                }
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError) as e:
        logger.warning(f"Could not get GPU memory info: {e}")

    return None


def check_vram_availability() -> Dict[str, Any]:
    """
    Check if there's enough VRAM for the configured number of workers.

    Returns:
        Dictionary with availability info and recommendations
    """
    gpu_info = get_gpu_memory_info()
    estimated_usage_gb = WORKER_COUNT * VRAM_PER_WORKER_GB

    result = {
        'worker_count': WORKER_COUNT,
        'estimated_usage_gb': estimated_usage_gb,
        'vram_per_worker_gb': VRAM_PER_WORKER_GB,
        'gpu_detected': gpu_info is not None,
        'sufficient_vram': False,
        'recommendation': 'Unable to check VRAM',
        'warnings': []
    }

    if gpu_info:
        free_gb = gpu_info['free_gb']
        total_gb = gpu_info['total_gb']
        used_gb = gpu_info['used_gb']

        result.update({
            'current_used_gb': used_gb,
            'current_free_gb': free_gb,
            'total_gb': total_gb,
            'sufficient_vram': free_gb >= estimated_usage_gb
        })

        if free_gb >= estimated_usage_gb + MIN_FREE_VRAM_GB:
            result['recommendation'] = f'Sufficient VRAM ({free_gb:.1f}GB free for {estimated_usage_gb}GB needed)'
        elif free_gb >= estimated_usage_gb:
            result['recommendation'] = f'Barely sufficient VRAM ({free_gb:.1f}GB free for {estimated_usage_gb}GB needed)'
            result['warnings'].append(f'Very little VRAM margin ({free_gb - estimated_usage_gb:.1f}GB)')
        else:
            result['recommendation'] = f'Insufficient VRAM ({free_gb:.1f}GB free, {estimated_usage_gb}GB needed)'
            result['warnings'].append(f'Need {estimated_usage_gb - free_gb:.1f}GB more VRAM')

        # Additional warnings
        if WORKER_COUNT > 1 and free_gb < estimated_usage_gb:
            single_usage = 1 * VRAM_PER_WORKER_GB
            if free_gb >= single_usage:
                result['warnings'].append(f'Consider reducing to 1 worker ({single_usage}GB)')

    return result


def get_worker_config() -> List[Dict[str, Any]]:
    """
    Generate worker configuration list.

    Returns:
        List of worker configurations with host, port, context info, and log file info
    """
    workers = []
    for i, port in enumerate(WORKER_PORTS):
        context_config = WORKER_CONTEXT_CONFIG.get(port, {
            "context_size": CONTEXT_STANDARD,
            "config_module": DEFAULT_CONFIG_MODULE
        })

        workers.append({
            "id": f"worker_{i+1}",
            "host": LOAD_BALANCER_HOST,
            "port": port,
            "url": f"http://{LOAD_BALANCER_HOST}:{port}",
            "log_file": f"llm_worker_{port}.log",
            "index": i,
            "context_size": context_config["context_size"],
            "config_module": context_config["config_module"]
        })
    return workers


def validate_configuration() -> List[str]:
    """
    Validate the current configuration and return any warnings/errors.

    Returns:
        List of validation messages (empty if all good)
    """
    warnings = []

    # Basic validation
    if WORKER_COUNT < 1:
        warnings.append("ERROR: WORKER_COUNT must be at least 1")

    if WORKER_COUNT > 4:
        warnings.append("WARNING: Running more than 4 workers may cause resource issues")

    # VRAM validation
    vram_check = check_vram_availability()
    if vram_check['gpu_detected']:
        if not vram_check['sufficient_vram']:
            warnings.append(f"ERROR: {vram_check['recommendation']}")
        else:
            if vram_check['warnings']:
                for warning in vram_check['warnings']:
                    warnings.append(f"WARNING: {warning}")
    else:
        warnings.append("WARNING: No GPU detected or nvidia-smi not available - cannot validate VRAM")

    # Other validation
    if HEALTH_CHECK_INTERVAL < 10:
        warnings.append("WARNING: Very frequent health checks may impact performance")

    if REQUEST_TIMEOUT < 60:
        warnings.append("WARNING: Low request timeout may cause LLM generation failures")

    return warnings


def print_configuration():
    """Print the current configuration for debugging."""
    print("Load Balancer Configuration:")
    print(f"   Worker Count: {WORKER_COUNT}")
    print(f"   Worker Ports: {WORKER_PORTS}")
    print(f"   Load Balancer Port: {LOAD_BALANCER_PORT}")
    print(f"   Health Check Interval: {HEALTH_CHECK_INTERVAL}s")
    print(f"   Request Timeout: {REQUEST_TIMEOUT}s")
    print(f"   Log Level: {LOG_LEVEL}")

    # Show VRAM information
    vram_check = check_vram_availability()
    if vram_check['gpu_detected']:
        print(f"\nGPU Memory Status:")
        print(f"   Current Usage: {vram_check['current_used_gb']:.1f}GB / {vram_check['total_gb']:.1f}GB")
        print(f"   Available: {vram_check['current_free_gb']:.1f}GB")
        print(f"   Estimated Need: {vram_check['estimated_usage_gb']}GB ({WORKER_COUNT} x {VRAM_PER_WORKER_GB}GB)")
        print(f"   {vram_check['recommendation']}")
    else:
        print("\nGPU Memory Status: Unable to detect GPU")

    # Show validation warnings
    warnings = validate_configuration()
    if warnings:
        print("\nConfiguration Warnings/Errors:")
        for warning in warnings:
            print(f"   {warning}")
    else:
        print("   Configuration validated successfully")


def get_configuration_summary() -> Dict[str, Any]:
    """Get configuration as a dictionary for API responses."""
    vram_check = check_vram_availability()
    warnings = validate_configuration()

    return {
        "worker_count": WORKER_COUNT,
        "worker_ports": WORKER_PORTS,
        "load_balancer_port": LOAD_BALANCER_PORT,
        "health_check_interval": HEALTH_CHECK_INTERVAL,
        "request_timeout": REQUEST_TIMEOUT,
        "load_balance_algorithm": LOAD_BALANCE_ALGORITHM,
        "estimated_vram_gb": WORKER_COUNT * VRAM_PER_WORKER_GB,
        "vram_status": vram_check,
        "configuration_valid": len([w for w in warnings if w.startswith("ERROR")]) == 0,
        "warnings_count": len([w for w in warnings if w.startswith("WARNING")]),
        "errors_count": len([w for w in warnings if w.startswith("ERROR")])
    }


# Environment-based overrides for common scenarios
def apply_environment_overrides():
    """Apply environment-based configuration overrides."""
    global WORKER_COUNT, WORKER_PORTS

    # Check for specific deployment modes
    deployment_mode = os.getenv("LB_DEPLOYMENT_MODE", "").lower()

    if deployment_mode == "single":
        WORKER_COUNT = 1
        WORKER_PORTS = [WORKER_BASE_PORT]
        logger.info("Environment override: Single instance mode activated")
    elif deployment_mode == "dual":
        WORKER_COUNT = 2
        WORKER_PORTS = list(range(WORKER_BASE_PORT, WORKER_BASE_PORT + 2))
        logger.info("Environment override: Dual instance mode activated")
    elif deployment_mode == "development":
        # Development mode: single instance, verbose logging
        WORKER_COUNT = 1
        WORKER_PORTS = [WORKER_BASE_PORT]
        os.environ["LB_LOG_LEVEL"] = "DEBUG"
        logger.info("Environment override: Development mode activated")


# Apply environment overrides on import
apply_environment_overrides()


if __name__ == "__main__":
    # When run as a script, show current configuration
    print_configuration()
    print(f"\nWorker Configuration:")
    for worker in get_worker_config():
        print(f"   {worker['id']}: {worker['url']} -> {worker['log_file']}")
