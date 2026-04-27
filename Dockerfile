FROM python:3.14-slim

# Set working directory
WORKDIR /app

# Install system dependencies (chromium: Plotly Kaleido / fig.write_image static export)
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron curl make \
    chromium \
    fonts-liberation \
    libx11-6 libxcb1 libxext6 libxrender1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Kaleido (choreographer) uses this before PATH / bundled Chrome lookup
ENV BROWSER_PATH=/usr/bin/chromium

# Install Poetry
RUN pip install poetry==2.3.4

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