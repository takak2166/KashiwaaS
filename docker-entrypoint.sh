#!/bin/bash
set -e

# Setup Elasticsearch indices if Elasticsearch is available
echo "Waiting for Elasticsearch to be ready..."
until curl -s http://elasticsearch:9200 > /dev/null; do
    echo "Elasticsearch is unavailable - sleeping"
    sleep 5
done

echo "Elasticsearch is up - setting up indices"
python scripts/setup_indices.py

# Start cron service if requested
if [ "$1" = "cron" ]; then
    echo "Starting cron service"
    service cron start
    
    # Keep container running
    if [ "$2" = "-f" ]; then
        echo "Running in foreground mode"
        tail -f /var/log/app/collector.log /var/log/app/daily_report.log /var/log/app/weekly_report.log
    fi
else
    # Execute the passed command
    exec "$@"
fi