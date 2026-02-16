"""
Load Balancer for Multiple LLM Instances

This service acts as a load balancer that distributes requests across multiple
LLM instances running on different ports. It provides automatic failover,
health monitoring, and request distribution.

The load balancer runs on port 8000 (same port the backend expects) and forwards
requests to available LLM worker instances.
"""

import logging
import asyncio
import httpx
import time
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import itertools
import json

# Import configuration
import load_balancer_config as config

# Setup logging
log_level = getattr(logging, config.LOG_LEVEL.upper())
logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="LLM Load Balancer")


# --- Configuration ---
class WorkerInstance:
    def __init__(self, worker_config: dict):
        self.id = worker_config["id"]
        self.host = worker_config["host"]
        self.port = worker_config["port"]
        self.url = worker_config["url"]
        self.log_file = worker_config["log_file"]
        self.index = worker_config["index"]
        self.context_size = worker_config.get("context_size", 3072)
        self.config_module = worker_config.get("config_module", "config")
        self.healthy = True
        self.last_health_check = 0
        self.total_requests = 0
        self.failed_requests = 0

    def __str__(self):
        return f"{self.id} {self.url} (healthy: {self.healthy})"

    def get_stats(self) -> dict:
        """Get worker statistics."""
        return {
            "id": self.id,
            "url": self.url,
            "healthy": self.healthy,
            "last_health_check": self.last_health_check,
            "total_requests": self.total_requests,
            "failed_requests": self.failed_requests,
            "success_rate": (
                (self.total_requests - self.failed_requests) / self.total_requests * 100
                if self.total_requests > 0 else 100
            )
        }


# Initialize worker instances from configuration
WORKER_INSTANCES = [WorkerInstance(worker_config) for worker_config in config.get_worker_config()]
logger.info(f"Configured {len(WORKER_INSTANCES)} worker instances: {[w.url for w in WORKER_INSTANCES]}")

# Load balancing configuration from config file
HEALTH_CHECK_INTERVAL = config.HEALTH_CHECK_INTERVAL
REQUEST_TIMEOUT = config.REQUEST_TIMEOUT
MAX_RETRIES = config.MAX_RETRIES

# Round-robin iterator for load balancing
worker_cycle = itertools.cycle(WORKER_INSTANCES)
last_worker_index = 0


# --- Health Monitoring ---
async def check_worker_health(worker: WorkerInstance) -> bool:
    """Check if a worker instance is healthy."""
    try:
        async with httpx.AsyncClient(timeout=config.HEALTH_CHECK_TIMEOUT) as client:
            response = await client.get(f"{worker.url}/health")
            worker.healthy = response.status_code == 200
            worker.last_health_check = time.time()

            if worker.healthy:
                logger.debug(f"Worker {worker.id} ({worker.url}) is healthy")
            else:
                logger.warning(f"Worker {worker.id} ({worker.url}) returned status {response.status_code}")

            return worker.healthy

    except Exception as e:
        worker.healthy = False
        worker.last_health_check = time.time()
        logger.warning(f"Worker {worker.id} ({worker.url}) health check failed: {e}")
        return False


async def periodic_health_checks():
    """Background task to periodically check worker health."""
    while True:
        logger.info("Performing health checks on all workers...")
        healthy_count = 0

        for worker in WORKER_INSTANCES:
            is_healthy = await check_worker_health(worker)
            if is_healthy:
                healthy_count += 1

        logger.info(f"Health check complete: {healthy_count}/{len(WORKER_INSTANCES)} workers healthy")

        if healthy_count == 0:
            logger.error("No healthy workers available!")

        await asyncio.sleep(HEALTH_CHECK_INTERVAL)


def get_healthy_workers() -> List[WorkerInstance]:
    """Get list of currently healthy workers."""
    return [worker for worker in WORKER_INSTANCES if worker.healthy]


def estimate_prompt_tokens(prompt: str) -> int:
    """Estimate number of tokens in a prompt (rough estimate: 4 chars per token)."""
    return len(prompt) // 4


def get_preferred_worker_for_prompt(prompt: str) -> Optional[WorkerInstance]:
    """Get the preferred worker based on prompt length and context requirements."""
    healthy_workers = get_healthy_workers()
    if not healthy_workers:
        return None

    estimated_tokens = estimate_prompt_tokens(prompt)

    # If prompt is long, prefer workers with large context windows
    if estimated_tokens > config.LARGE_CONTEXT_THRESHOLD // 4:  # Convert char threshold to token threshold
        large_context_workers = [w for w in healthy_workers if w.context_size >= config.CONTEXT_LARGE]
        if large_context_workers:
            logger.info(f"Routing long prompt ({estimated_tokens} estimated tokens) to large context worker")
            return large_context_workers[0]  # Use first available large context worker

    # For short prompts or if no large context worker available, use any healthy worker
    # Prefer standard context workers to save resources
    standard_context_workers = [w for w in healthy_workers if w.context_size < config.CONTEXT_LARGE]
    if standard_context_workers:
        return standard_context_workers[0]

    # Fallback to any healthy worker
    return healthy_workers[0]


def get_next_worker() -> Optional[WorkerInstance]:
    """Get the next available worker using round-robin."""
    healthy_workers = get_healthy_workers()

    if not healthy_workers:
        logger.error("No healthy workers available")
        return None

    # Simple round-robin among healthy workers
    global last_worker_index
    last_worker_index = (last_worker_index + 1) % len(healthy_workers)
    selected_worker = healthy_workers[last_worker_index]

    logger.debug(f"Selected worker: {selected_worker.url}")
    return selected_worker


# --- Request Forwarding ---
async def forward_request(worker: WorkerInstance, request_data: dict, stream: bool = False):
    """Forward a request to a worker instance."""
    try:
        worker.total_requests += 1

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            if stream:
                # Handle streaming requests
                async with client.stream(
                    "POST",
                    f"{worker.url}/generate",
                    json=request_data,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status_code != 200:
                        raise HTTPException(status_code=response.status_code,
                                          detail=f"Worker error: {response.text}")

                    async def stream_generator():
                        async for chunk in response.aiter_text():
                            yield chunk

                    return StreamingResponse(stream_generator(), media_type="text/plain")
            else:
                # Handle non-streaming requests
                response = await client.post(
                    f"{worker.url}/generate",
                    json=request_data,
                    headers={"Content-Type": "application/json"}
                )

                if response.status_code != 200:
                    raise HTTPException(status_code=response.status_code,
                                      detail=f"Worker error: {response.text}")

                return response.json()

    except Exception as e:
        worker.failed_requests += 1
        logger.error(f"Request failed on worker {worker.url}: {e}")
        raise


# --- API Endpoints ---
@app.post("/generate")
async def generate(request: Request):
    """
    Generate text using an available LLM worker.
    Supports intelligent routing based on prompt length and context requirements.
    """
    try:
        request_data = await request.json()
        stream = request_data.get("stream", False)
        prompt = request_data.get("prompt", "")

        # Use intelligent routing to select the best worker for this prompt
        worker = get_preferred_worker_for_prompt(prompt)
        if not worker:
            raise HTTPException(status_code=503,
                              detail="No healthy workers available")

        # Try the selected worker first
        try:
            estimated_tokens = estimate_prompt_tokens(prompt)
            logger.info(f"Forwarding request ({estimated_tokens} est. tokens) to {worker.url} (context: {worker.context_size}, stream: {stream})")
            return await forward_request(worker, request_data, stream)

        except Exception as e:
            logger.warning(f"Request failed on {worker.url}, trying backup worker: {e}")

            # Mark this worker as potentially unhealthy and try another
            worker.healthy = False

            # Try one more healthy worker (fallback to round-robin)
            backup_worker = get_next_worker()
            if backup_worker and backup_worker != worker:
                logger.info(f"Retrying request on backup worker {backup_worker.url} (context: {backup_worker.context_size})")
                return await forward_request(backup_worker, request_data, stream)
            else:
                raise HTTPException(status_code=503,
                                  detail="All workers failed to process request")

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in request")
    except Exception as e:
        logger.error(f"Load balancer error: {e}")
        raise HTTPException(status_code=500, detail=f"Load balancer error: {str(e)}")


@app.get("/health")
async def health_check():
    """Health check endpoint that reports the status of all workers and configuration."""
    healthy_workers = get_healthy_workers()

    # Get chat format from first healthy worker to maintain compatibility
    chat_format = "unknown"  # Default fallback
    if healthy_workers:
        try:
            async with httpx.AsyncClient(timeout=config.HEALTH_CHECK_TIMEOUT) as client:
                worker_health_response = await client.get(f"{healthy_workers[0].url}/health")
                if worker_health_response.status_code == 200:
                    worker_health_data = worker_health_response.json()
                    detected_format = worker_health_data.get("chat_format", "unknown")
                    if detected_format:  # Only use if not None/empty
                        chat_format = detected_format
                        logger.debug(f"Detected chat format from worker: {chat_format}")
        except Exception as e:
            logger.warning(f"Could not get chat format from worker, using default: {e}")

    return {
        "status": "ok" if len(healthy_workers) > 0 else "degraded",
        "service": "llm-load-balancer",
        "chat_format": chat_format,  # Pass through chat format for compatibility
        "total_workers": len(WORKER_INSTANCES),
        "healthy_workers": len(healthy_workers),
        "configuration": config.get_configuration_summary(),
        "workers": [worker.get_stats() for worker in WORKER_INSTANCES]
    }


@app.get("/stats")
async def get_stats():
    """Get detailed statistics about load balancing."""
    total_requests = sum(w.total_requests for w in WORKER_INSTANCES)
    total_failed = sum(w.failed_requests for w in WORKER_INSTANCES)

    return {
        "total_requests": total_requests,
        "total_failed": total_failed,
        "success_rate": (total_requests - total_failed) / total_requests * 100 if total_requests > 0 else 100,
        "healthy_workers": len(get_healthy_workers()),
        "total_workers": len(WORKER_INSTANCES),
        "configuration": config.get_configuration_summary(),
        "workers": [worker.get_stats() for worker in WORKER_INSTANCES]
    }


# --- Startup Event ---
@app.on_event("startup")
async def startup_event():
    """Initialize the load balancer and start health monitoring."""
    logger.info("Starting LLM Load Balancer")

    # Show configuration
    config.print_configuration()

    # Show validation warnings if any
    warnings = config.validate_configuration()
    if warnings:
        for warning in warnings:
            if warning.startswith("ERROR"):
                logger.error(warning)
            else:
                logger.warning(warning)

    logger.info(f"Configured workers: {[str(w) for w in WORKER_INSTANCES]}")

    # Perform initial health checks
    logger.info("Performing initial health checks...")
    healthy_count = 0
    for worker in WORKER_INSTANCES:
        is_healthy = await check_worker_health(worker)
        if is_healthy:
            healthy_count += 1

    logger.info(f"Initial health check complete: {healthy_count}/{len(WORKER_INSTANCES)} workers ready")

    if healthy_count == 0:
        logger.error("No workers are healthy! Load balancer will not function properly.")

    # Start background health monitoring
    asyncio.create_task(periodic_health_checks())


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting LLM Load Balancer on port {config.LOAD_BALANCER_PORT}...")
    uvicorn.run(app, host="0.0.0.0", port=config.LOAD_BALANCER_PORT)
