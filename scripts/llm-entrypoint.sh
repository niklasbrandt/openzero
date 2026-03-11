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

# Prune stale models — delete any .gguf files in MODEL_DIR that are not
# in the KEEP_MODELS whitelist. KEEP_MODELS is a comma-separated list of
# all currently active model filenames across ALL tiers (set via docker-compose).
# This prevents the volume from accumulating gigabytes of abandoned models
# AND prevents each container from deleting the other tier's model.
echo "Checking for stale models in ${MODEL_DIR}..."
# Build an associative list of models to keep
KEEP="${KEEP_MODELS:-$MODEL_FILE}"
find "$MODEL_DIR" -maxdepth 1 -name "*.gguf" | while read -r f; do
	FNAME="$(basename "$f")"
	# Check if this file is in the keep list
	if echo ",$KEEP," | grep -qF ",${FNAME},"; then
		: # keep it
	else
		SIZE_MB=$(du -sm "$f" 2>/dev/null | cut -f1)
		echo "Removing stale model: ${FNAME} (${SIZE_MB} MB)"
		rm -f "$f"
	fi
done

# Batch size for prompt evaluation — larger = faster TTFT but more RAM.
# Default 512 is a good balance. Set via BATCH_SIZE env var.
BATCH="${BATCH_SIZE:-512}"

# Parallel slots — 1 for a single-user personal assistant.
# Increasing this multiplies KV cache memory by N. Set via PARALLEL env var.
PARALLEL="${PARALLEL:-1}"

echo "Starting llama-server on port ${PORT}..."
echo "  Threads: ${THREADS}"
echo "  Context: ${CTX_SIZE}"
echo "  Max predict: ${N_PREDICT}"
echo "  Batch size: ${BATCH}"
echo "  Parallel slots: ${PARALLEL}"
echo "  Extra args: ${EXTRA_ARGS}"

exec /app/llama-server \
	--model "$MODEL_PATH" \
	--host 0.0.0.0 \
	--port "${PORT}" \
	--threads "${THREADS}" \
	--threads-batch "${THREADS}" \
	--ctx-size "${CTX_SIZE}" \
	--n-predict "${N_PREDICT}" \
	--batch-size "${BATCH}" \
	--parallel "${PARALLEL}" \
	--no-mmap \
	--mlock \
	--cont-batching \
	${EXTRA_ARGS}
