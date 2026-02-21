# Build Dashboard
FROM node:20-slim AS dashboard-build
WORKDIR /dashboard
COPY src/dashboard/package*.json ./
RUN npm install
COPY src/dashboard/ ./
RUN npm run build

# Final Backend Image
FROM python:3.12-slim
WORKDIR /app
COPY src/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/backend/app/ ./app/
COPY --from=dashboard-build /dashboard/dist/ ./static/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
