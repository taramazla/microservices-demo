# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories for models and logs
RUN mkdir -p /app/models /app/logs /app/data

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV MODEL_PATH=/app/models
ENV LOG_PATH=/app/logs

# Run as non-root user
RUN useradd -m -u 1000 scheduler && \
    chown -R scheduler:scheduler /app
USER scheduler

# Expose ports for metrics and API
EXPOSE 8000 9090

# Start the scheduler
CMD ["python", "-u", "main.py"]
