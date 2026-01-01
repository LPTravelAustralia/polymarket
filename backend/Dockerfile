FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for caching
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy source code
COPY src/ ./src/
COPY backend/ ./backend/

WORKDIR /app/backend

EXPOSE 8000

CMD ["python", "main.py"]
