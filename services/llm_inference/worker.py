# services/llm_inference/worker.py
import logging
import hashlib
import time
import sys
import os
import importlib
from functools import lru_cache
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from llama_cpp import Llama
from starlette.responses import StreamingResponse

# Determine which config to use based on command line arguments
config_module_name = "config"  # default
if len(sys.argv) > 2:
    # Format: python worker.py <port> <config_module>
    config_module_name = sys.argv[2]

# Import configurations from the specified config file
config = importlib.import_module(config_module_name)

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- Pydantic Models for API ---
# This defines the contract for the /generate endpoint
class GenerationRequest(BaseModel):
    prompt: str
    max_tokens: int = Field(default=config.DEFAULT_MAX_TOKENS)
    temperature: float = Field(default=config.DEFAULT_TEMP)
    top_p: float = Field(default=config.DEFAULT_TOP_P)
    top_k: int = Field(default=config.DEFAULT_TOP_K)
    repeat_penalty: float = Field(default=config.DEFAULT_REPEAT_PENALTY)
    stop: Optional[List[str]] = Field(default=config.STOP_SEQUENCES)
    stream: bool = Field(default=False)


# --- FastAPI App and Model Loading ---
app = FastAPI(title="LLM Inference Worker")


def load_model():
    """Loads the Llama model with a fallback for memory locking issues."""
    try:
        logger.info(
            f"Attempting to load LLM model from: {config.MODEL_PATH} with mlock..."
        )
        llm = Llama(
            model_path=config.MODEL_PATH,
            n_ctx=config.N_CTX,
            n_gpu_layers=config.N_GPU_LAYERS,
            n_threads=config.N_THREADS,
            n_batch=config.N_BATCH,
            use_mmap=config.USE_MMAP,
            use_mlock=config.USE_MLOCK,
            flash_attn=config.FLASH_ATTN,
            verbose=True,  # Enable verbose to debug GPU loading
            seed=config.SEED,
        )
        logger.info("LLM model loaded successfully with memory locking.")
        return llm
    except Exception as e:
        if "mlock" in str(e).lower() or "cannot allocate memory" in str(e).lower():
            logger.warning("Failed to load with mlock, retrying without...")
            llm = Llama(
                model_path=config.MODEL_PATH,
                n_ctx=config.N_CTX,
                n_gpu_layers=config.N_GPU_LAYERS,
                n_threads=config.N_THREADS,
                n_batch=config.N_BATCH,
                use_mmap=config.USE_MMAP,
                use_mlock=False,  # Disable memory locking
                flash_attn=config.FLASH_ATTN,
                verbose=True,  # Enable verbose to debug GPU loading
                seed=config.SEED,
            )
            logger.info("LLM model loaded successfully WITHOUT memory locking.")
            return llm
        else:
            logger.critical(f"Failed to load the LLM model: {e}", exc_info=True)
            raise


def warmup_model(llm_instance):
    """Perform a warmup prompt to ensure the model is fully ready."""
    if not config.ENABLE_WARMUP:
        return

    try:
        logger.info("Performing LLM model warmup...")
        warmup_start = time.time()

        # Send a simple warmup prompt
        result = llm_instance(
            prompt=config.WARMUP_PROMPT,
            max_tokens=config.WARMUP_MAX_TOKENS,
            temperature=0.1,
            stop=config.STOP_SEQUENCES,
        )

        warmup_time = time.time() - warmup_start
        response_text = result["choices"][0]["text"]
        logger.info(
            f"LLM model warmup completed in {warmup_time:.2f}s - Response: '{response_text.strip()}'"
        )

    except Exception as e:
        logger.warning(f"LLM model warmup failed (non-critical): {e}")


llm = load_model()

# Log the detected chat format
chat_format = config.get_chat_format()
logger.info(
    f"Using chat format: {chat_format.name} for model: {config.MODEL_FILENAME}"
)
logger.info(f"Stop sequences: {chat_format.get_stop_sequences()}")

# Warmup the model to ensure it's fully ready
warmup_model(llm)

# --- Response Cache ---
# Simple cache for non-streaming responses to avoid recomputation
response_cache = {}


def get_cache_key(request: GenerationRequest) -> str:
    """Generate a cache key for the request (only for non-streaming)."""
    if request.stream:
        return None

    cache_data = f"{request.prompt}|{request.max_tokens}|{request.temperature}|{request.top_p}|{request.top_k}|{request.repeat_penalty}|{request.stop}"
    return hashlib.md5(cache_data.encode()).hexdigest()


# --- API Endpoint ---
@app.post("/generate")
async def generate(request: GenerationRequest):
    """
    Receives a prompt and generates text using the loaded Llama model.
    Supports both streaming and non-streaming responses.
    """
    try:
        # Check cache for non-streaming requests
        if not request.stream:
            cache_key = get_cache_key(request)
            if cache_key and cache_key in response_cache:
                logger.info("Cache hit - returning cached response")
                return response_cache[cache_key]

        if request.stream:
            # For streaming responses, we return a StreamingResponse that yields tokens.
            def stream_generator():
                streamer = llm(
                    prompt=request.prompt,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    top_p=request.top_p,
                    top_k=request.top_k,
                    repeat_penalty=request.repeat_penalty,
                    stop=request.stop,
                    stream=True,
                )
                for chunk in streamer:
                    if "choices" in chunk and len(chunk["choices"]) > 0:
                        token = chunk["choices"][0].get("text", "")
                        yield token

            return StreamingResponse(stream_generator(), media_type="text/plain")

        else:
            # For non-streaming, we make a blocking call and return the full response.
            result = llm(
                prompt=request.prompt,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p,
                top_k=request.top_k,
                repeat_penalty=request.repeat_penalty,
                stop=request.stop,
            )
            response_text = result["choices"][0]["text"]

            # Clean the response using the chat format's cleaning method
            cleaned_response = chat_format.clean_response(response_text)
            response_obj = {"response": cleaned_response}

            # Cache the response for future requests (with simple size limit)
            cache_key = get_cache_key(request)
            if cache_key and len(response_cache) < 1000:  # Simple cache size limit
                response_cache[cache_key] = response_obj
                logger.info("Response cached")

            return response_obj

    except Exception as e:
        logger.error(f"Error during LLM model generation: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Error during LLM model generation."
        )


@app.get("/health")
def health_check():
    """A simple endpoint to check if the LLM worker service is running."""
    chat_format = config.get_chat_format()
    return {
        "status": "ok",
        "model_loaded": config.MODEL_FILENAME,
        "chat_format": chat_format.name,
        "service": "llm-worker",
    }


if __name__ == "__main__":
    import uvicorn

    # Get port from command line argument or environment variable
    port = 8010  # default port
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            logger.error(f"Invalid port number: {sys.argv[1]}")
            sys.exit(1)
    elif "LLM_WORKER_PORT" in os.environ:
        try:
            port = int(os.environ["LLM_WORKER_PORT"])
        except ValueError:
            logger.error(f"Invalid port in LLM_WORKER_PORT: {os.environ['LLM_WORKER_PORT']}")
            sys.exit(1)

    # Log the configuration being used
    context_size = getattr(config, 'N_CTX', 'unknown')
    logger.info(f"Starting LLM Worker on port {port} with config {config_module_name} (context: {context_size} tokens)...")
    uvicorn.run(app, host="0.0.0.0", port=port)
