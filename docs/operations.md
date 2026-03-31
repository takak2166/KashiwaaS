# Deployment and scaling

## 10. Deployment and operations

### Initial setup

1. Create Elasticsearch index templates
2. Install the Kuromoji analysis plugin
3. Create Kibana dashboards
4. Configure Slack bot authentication

### Backup

- Daily Elasticsearch snapshots
- Track config and code in Git

### Monitoring

- Elasticsearch cluster health
- Crawler / job status
- Error alerts to Slack

### Performance tuning

- Tune bulk batch size (e.g. 500 documents)
- Tune Elasticsearch cache sizes
- Adjust shard count as data grows

## 11. Extensibility and future work

### Possible extensions

- Multi-channel analysis
- Sentiment / “team mood” scoring
- User interaction network analysis
- Active-hours analysis and optimal posting time hints

### Scaling

- Elasticsearch clustering for larger data
- Async ingestion for throughput
- Index partitioning for search performance
