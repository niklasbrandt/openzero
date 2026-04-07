#!/bin/bash
set -e

# Inject the openZero dashboard nav link into Planka's EJS template.
# Idempotent: only patches if not already present, so container restarts are safe.
# The sed replaces the closing </head> tag once, inserting our deferred script.
# Note: in Planka 2.1.0+ the template is index.ejs (was index.html in 2.0.x).
if ! grep -q 'oz-nav.js' /app/views/index.ejs; then
	sed -i 's|</head>|<script src="/assets/oz-nav.js" defer></script></head>|' /app/views/index.ejs
fi

# Hand off to the original Node.js Docker entrypoint which runs the CMD (./start.sh).
exec /usr/local/bin/docker-entrypoint.sh "$@"
