#!/bin/bash
# ──────────────────────────────────────────────────────────────
# openZero LLM Entrypoint (llama-server / llama.cpp)
# ──────────────────────────────────────────────────────────────
# Downloads a GGUF model if not present, then starts llama-server.
#
# Required environment variables:
#   MODEL_URL   - Hugging Face direct download URL for the GGUF file
#   MODEL_FILE  - Filename to save as (e.g. phi-4-mini-q4_0.gguf)
#   PORT        - Port to listen on (e.g. 8081)
#   THREADS     - Number of CPU threads to use
#   CTX_SIZE    - Context window size (tokens)
#   N_PREDICT   - Max tokens to generate per request
#
# Optional:
#   EXTRA_ARGS  - Additional llama-server flags (e.g. "--flash-attn")

set -e

MODEL_DIR="/models"
MODEL_PATH="${MODEL_DIR}/${MODEL_FILE}"

# Ensure model directory exists
mkdir -p "$MODEL_DIR"

# Download model if not present
if [ ! -f "$MODEL_PATH" ]; then
	echo "Model not found at ${MODEL_PATH}. Downloading..."
	echo "URL: ${MODEL_URL}"
	curl -L --progress-bar -o "${MODEL_PATH}.tmp" "$MODEL_URL"
	mv "${MODEL_PATH}.tmp" "$MODEL_PATH"
	echo "Download complete: ${MODEL_FILE}"
else
	echo "Model already present: ${MODEL_FILE}"
fi

echo "Starting llama-server on port ${PORT}..."
echo "  Threads: ${THREADS}"
echo "  Context: ${CTX_SIZE}"
echo "  Max predict: ${N_PREDICT}"

exec /app/llama-server \
	--model "$MODEL_PATH" \
	--host 0.0.0.0 \
	--port "${PORT}" \
	--threads "${THREADS}" \
	--ctx-size "${CTX_SIZE}" \
	--n-predict "${N_PREDICT}" \
	--mlock \
	--cont-batching \
	${EXTRA_ARGS}
