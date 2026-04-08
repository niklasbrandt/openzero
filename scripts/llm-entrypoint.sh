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

# ── Header Validation (Internal Model Name) ───────────────────
# Read the first 1KB of the file and look for the internal model name string.
# Most GGUF files contain 'general.name' or 'general.basename' early in the header.
echo "Verifying internal model header..."
HEADER_SIG=$(head -c 1024 "$MODEL_PATH" | tr -dc '[:print:]' | grep -oEi "Qwen3-[0-9.]+B|Llama-[0-9.]+B" | head -n1 | tr '[:lower:]' '[:upper:]')
if [[ -n "$HEADER_SIG" && -n "$FILE_SIG" ]]; then
	# We only enforce this for Qwen3 models since we know the signature format precisely.
	if [[ "$HEADER_SIG" == "QWEN3"* ]]; then
		if [[ "$HEADER_SIG" != *"$FILE_SIG"* ]]; then
			echo "❌ ERROR: Internal header mismatch!"
			echo "  Filename claims: ${FILE_SIG}"
			echo "  Header contains: ${HEADER_SIG}"
			echo "This file is internally identified as ${HEADER_SIG} regardless of its filename."
			echo "Please use the correct model for this tier."
			exit 1
		fi
		echo "Header validation passed: ${HEADER_SIG}"
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

# ── Hardware Auto-Detection ──────────────────────────────────────────────────
# Reads total RAM and CPU count from the host and selects a hardware profile.
# This means openZero works out of the box on any machine — from a Raspberry
# Pi 5 8 GB to a 64 GB homelab — with no manual tuning required.
# You can still override any individual value by setting LLM_LOCAL_* in .env.
TOTAL_RAM_KB=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}')
TOTAL_RAM_GB=$(awk "BEGIN { printf \"%d\", ${TOTAL_RAM_KB:-0} / 1048576 }")
CPU_THREADS=$(nproc 2>/dev/null || echo 4)

if   [ "$TOTAL_RAM_GB" -lt 10 ]; then
	_PROFILE="Minimal — Pi 5 / 8 GB VPS"
	_AUTO_CTX=8192;  _AUTO_PREDICT=512;  _AUTO_BATCH=256; _AUTO_CACHE=128
	_AUTO_NO_MMAP=0; _AUTO_MLOCK=0
elif [ "$TOTAL_RAM_GB" -lt 16 ]; then
	_PROFILE="Standard — 12 GB VPS"
	_AUTO_CTX=16384; _AUTO_PREDICT=512;  _AUTO_BATCH=512; _AUTO_CACHE=256
	_AUTO_NO_MMAP=1; _AUTO_MLOCK=1
elif [ "$TOTAL_RAM_GB" -lt 32 ]; then
	_PROFILE="Comfortable — 24 GB"
	_AUTO_CTX=32768; _AUTO_PREDICT=1024; _AUTO_BATCH=512; _AUTO_CACHE=512
	_AUTO_NO_MMAP=1; _AUTO_MLOCK=1
else
	_PROFILE="High-end — 32 GB+"
	_AUTO_CTX=32768; _AUTO_PREDICT=1024; _AUTO_BATCH=512; _AUTO_CACHE=2048
	_AUTO_NO_MMAP=1; _AUTO_MLOCK=1
fi

echo "Hardware: ${TOTAL_RAM_GB} GB RAM, ${CPU_THREADS} CPU threads → auto-profile: ${_PROFILE}"

# Merge: explicit .env overrides win; auto-detected values are the fallback.
THREADS="${THREADS:-$CPU_THREADS}"
CTX_SIZE="${CTX_SIZE:-$_AUTO_CTX}"
N_PREDICT="${N_PREDICT:-$_AUTO_PREDICT}"
BATCH="${BATCH_SIZE:-$_AUTO_BATCH}"
PARALLEL="${PARALLEL:-1}"
CACHE="${LLM_CACHE_RAM:-$_AUTO_CACHE}"
NO_MMAP="${LLM_LOCAL_NO_MMAP:-$_AUTO_NO_MMAP}"
MLOCK="${LLM_LOCAL_MLOCK:-$_AUTO_MLOCK}"

echo "Starting llama-server on port ${PORT}..."
echo "  Profile: ${_PROFILE}"
echo "  Threads: ${THREADS}"
echo "  Context: ${CTX_SIZE}"
echo "  Max predict: ${N_PREDICT}"
echo "  Batch size: ${BATCH}"
echo "  Parallel slots: ${PARALLEL}"
echo "  Cache RAM: ${CACHE} MiB"
echo "  no-mmap: ${NO_MMAP} | mlock: ${MLOCK}"
echo "  Extra args: ${EXTRA_ARGS}"

MEMORY_FLAGS=""
[[ "${NO_MMAP}" == "1" ]] && MEMORY_FLAGS="${MEMORY_FLAGS} --no-mmap"
[[ "${MLOCK}" == "1" ]] && MEMORY_FLAGS="${MEMORY_FLAGS} --mlock"

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
	--cache-ram "${CACHE}" \
	--cont-batching \
	${MEMORY_FLAGS} \
	${EXTRA_ARGS}
