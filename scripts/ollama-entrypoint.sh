#!/bin/bash
# Start Ollama server in the background
ollama serve &

# Wait for the server to be ready
echo "Waiting for Ollama to start..."
until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
  sleep 2
done
echo "Ollama is ready."

# Pull model if not already present
if [ -n "$OLLAMA_MODEL" ]; then
  if ! ollama list | grep -q "$OLLAMA_MODEL"; then
    echo "Pulling $OLLAMA_MODEL model..."
    ollama pull "$OLLAMA_MODEL"
    echo "Model pulled successfully."
  else
    echo "Model $OLLAMA_MODEL already present."
  fi
fi

# Keep Ollama running in the foreground
wait
