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

# ── Signature Validation (URL vs Filename) ──────────────────────
# Extract parameter signature (e.g. 0.6B, 8B, 14B) from URL and File
URL_SIG=$(echo "$MODEL_URL" | grep -oEi '[0-9.]+[BM]' | tr '[:lower:]' '[:upper:]' | head -n1)
FILE_SIG=$(echo "$MODEL_FILE" | grep -oEi '[0-9.]+[BM]' | tr '[:lower:]' '[:upper:]' | head -n1)

if [[ -n "$URL_SIG" && -n "$FILE_SIG" && "$URL_SIG" != "$FILE_SIG" ]]; then
	echo "❌ ERROR: Resource signature conflict!"
	echo "  URL signature: ${URL_SIG}"
	echo "  File signature: ${FILE_SIG}"
	echo "This suggests a large model (e.g. ${URL_SIG}) is being forced into a container labeled as ${FILE_SIG}."
	echo "Refusing to start to prevent system instability."
	exit 1
fi

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

# ── Size Validation (Physical vs Filename Claim) ──────────────
# Prevent 'lying' filenames by checking floor file size against claimed params.
# A 0.6B Q4 model is ~400MB. If the file is 8GB, it's NOT a 0.6B model.
if [[ -n "$FILE_SIG" ]]; then
	# Convert signature to number (B = 10^9)
	NUM=$(echo "$FILE_SIG" | sed 's/B//')
	# Rough estimate: Q4_K_M is ~0.6 GB per 1B parameters
	EXPECTED_GB=$(awk "BEGIN {print $NUM * 0.6}")
	# Max tolerance: 1.8x the base estimate (allows for higher quants like Q8)
	MAX_GB=$(awk "BEGIN {print $EXPECTED_GB * 1.8}")
	# Actual size on disk
	ACTUAL_BYTES=$(stat -c%s "$MODEL_PATH")
	ACTUAL_GB=$(awk "BEGIN {print $ACTUAL_BYTES / (1024^3)}")

	# If filename claims < 1B but file is > 2GB, or if > 1.8x expected.
	# We use a floor of 1.0GB for very small models to avoid false positives.
	IS_SUSPICIOUS=0
	if [ "$(awk "BEGIN {print ($ACTUAL_GB > 1.0 && $NUM < 1.0) ? 1 : 0}")" -eq 1 ]; then
		IS_SUSPICIOUS=1
	elif [ "$(awk "BEGIN {print ($ACTUAL_GB > $MAX_GB && $EXPECTED_GB > 0.5) ? 1 : 0}")" -eq 1 ]; then
		IS_SUSPICIOUS=1
	fi

	if [[ "$IS_SUSPICIOUS" -eq 1 ]]; then
		echo "❌ ERROR: Physical size mismatch!"
		echo "  Claimed params: ${FILE_SIG} (~${EXPECTED_GB} GB expected for Q4)"
		echo "  Actual size:   $(printf "%.2f" "$ACTUAL_GB") GB"
		echo "The file is physically too large to be a ${FILE_SIG} model."
		echo "This happens if you renamed a 14B model to '0.6B' to bypass UI warnings."
		echo "Please fix your .env and delete the stale file: rm ${MODEL_PATH}"
		exit 1
	fi
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
