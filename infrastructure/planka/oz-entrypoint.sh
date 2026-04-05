#!/bin/bash
set -e

# Inject the openZero dashboard nav link into Planka's HTML template.
# Idempotent: only patches if not already present, so container restarts are safe.
# The sed replaces the closing </head> tag once, inserting our deferred script.
if ! grep -q 'oz-nav.js' /app/views/index.html; then
	sed -i 's|</head>|<script src="/oz-nav.js" defer></script></head>|' /app/views/index.html
fi

# Hand off to the original Node.js Docker entrypoint which runs the CMD (./start.sh).
exec /usr/local/bin/docker-entrypoint.sh "$@"
