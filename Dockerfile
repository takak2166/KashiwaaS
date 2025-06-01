FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron curl make\
    # Dependencies for kaleido
    libx11-6 libxcb1 libxext6 libxrender1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry==2.1.1

# Copy poetry configuration files
COPY pyproject.toml poetry.lock* README.md ./

# Configure poetry to not use virtualenvs
RUN poetry config virtualenvs.create false

# Copy application code
COPY . .

# Install dependencies
RUN poetry install --no-interaction --no-ansi

# Setup cron jobs
COPY crontab /etc/cron.d/app-cron
RUN chmod 0644 /etc/cron.d/app-cron && \
    crontab /etc/cron.d/app-cron

# Create log directory
RUN mkdir -p /var/log/app

# Set entrypoint
ENTRYPOINT ["./docker-entrypoint.sh"]

# Default command
CMD ["cron", "-f"]