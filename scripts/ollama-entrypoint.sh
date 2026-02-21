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
if ! ollama list | grep -q "llama3.1"; then
  echo "Pulling llama3.1:8b model..."
  ollama pull llama3.1:8b
  echo "Model pulled successfully."
else
  echo "Model llama3.1:8b already present."
fi

# Keep Ollama running in the foreground
wait
