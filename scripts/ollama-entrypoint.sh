#!/bin/bash
# Start Ollama server in the background
ollama serve &

# Wait for the server to be ready
echo "Waiting for Ollama to start..."
until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
  sleep 2
done
echo "Ollama is ready."

# Pull models if not already present
pull_model() {
  local model="$1"
  if [ -n "$model" ]; then
    if ollama list | grep -q "$(echo "$model" | cut -d: -f1)"; then
      echo "Model $model already present."
    else
      echo "Pulling $model..."
      ollama pull "$model"
      echo "$model pulled successfully."
    fi
  fi
}

# Pull fast model (primary, used by default)
pull_model "$OLLAMA_MODEL"

# Pull smart model (used for complex reasoning tasks)
pull_model "$OLLAMA_MODEL_SMART"

# Keep Ollama running in the foreground
wait
