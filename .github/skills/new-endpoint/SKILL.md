---
name: new-endpoint
description: "Scaffold a new FastAPI REST endpoint with Pydantic models, service function stub, and dashboard integration pattern."
---

# New Endpoint Skill

Creates a complete FastAPI endpoint scaffold following openZero conventions.

## Steps

1. **Ask** for:
   - Endpoint path (e.g. `/api/dashboard/weather`).
   - HTTP method (GET, POST, PUT, DELETE).
   - Brief description of what it returns/accepts.

2. **Create the endpoint** in `src/backend/app/api/dashboard.py` using the template in `references/endpoint-template.py`. Adapt:
   - Route path and method.
   - Pydantic request/response models.
   - Authentication: all dashboard endpoints use `Depends(require_auth)`.

3. **Create service function** in the appropriate service file under `src/backend/app/services/`:
   - Use `async def`.
   - Tab indentation.
   - Proper error handling (no bare `except:`).

4. **Dashboard integration pattern** (if the endpoint serves a component):
   ```typescript
   private async fetchData() {
       try {
           const res = await fetch('/api/dashboard/weather');
           if (!res.ok) throw new Error(`HTTP ${res.status}`);
           const data = await res.json();
           // update component state
           this.render();
       } catch (e) {
           console.error('Failed to fetch:', e);
       }
   }
   ```

5. **Verify:**
   ```bash
   ruff check src/backend/
   cd src/dashboard && npx tsc --noEmit
   ```
