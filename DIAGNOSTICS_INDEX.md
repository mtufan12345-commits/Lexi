# Lexi AI - Diagnostics & Health Check Index

## Quick Status

**Last Check**: 2025-10-29 21:12:32 UTC  
**Overall Status**: OPERATIONAL WITH WARNINGS  
**Critical Issues**: 2 (Worker Timeouts, Memory Spikes)

## Reports Available

1. **HEALTH_CHECK_REPORT_2025-10-29.txt** - Full comprehensive report
   - Service status
   - Database connectivity
   - System resources
   - Critical issues & analysis
   - Recommended fixes (prioritized)
   - Deployment checklist
   - Troubleshooting guide

## Service Status Summary

| Service | Status | Port | Details |
|---------|--------|------|---------|
| Gunicorn (Flask) | RUNNING ✓ | 5000 | 19 workers, 598 MB/worker avg |
| Memgraph | RUNNING ✓ | 7687 | Docker container, up 3 hours |
| PostgreSQL | CONNECTED ✓ | 5432 | Neon Cloud, 16.9 |
| Supervisord | RUNNING ✓ | - | Monitoring server_monitor.py |

## Critical Issues

### Issue 1: Worker Timeouts
- **Status**: 2 incidents in last 100 log entries
- **Cause**: Request processing > 120s limit
- **Frequency**: Every 15-20 minutes during batch ops
- **Fix**: Increase gunicorn timeout to 300s
- **Priority**: HIGH

### Issue 2: Out of Memory
- **Status**: 2 incidents correlated with timeouts
- **Cause**: Worker memory spikes during complex operations
- **Fix**: Reduce max_requests to force worker recycling
- **Priority**: HIGH

### Issue 3: Debug Mode Enabled
- **Status**: FLASK_DEBUG=1 in production
- **Impact**: Adds 100-200 MB overhead per worker
- **Fix**: Change to FLASK_DEBUG=0 in systemd service
- **Priority**: MEDIUM

## Quick Fixes (Priority 1)

### 1. Increase Gunicorn Timeout
```bash
# File: /var/www/lexi/gunicorn.conf.py
# Line 34: Change from 120 to 300
timeout = 300
graceful_timeout = 300
```

### 2. Reduce Worker Max Requests
```bash
# File: /var/www/lexi/gunicorn.conf.py
# Line 74: Change from 1000 to 500
max_requests = int(os.getenv('MAX_REQUESTS', 500))
```

### 3. Disable Flask Debug Mode
```bash
# File: /etc/systemd/system/lexi.service
# Remove or change the FLASK_DEBUG line
# Environment="FLASK_DEBUG=1"  <- DELETE THIS LINE

# Then restart:
systemctl restart lexi
```

## System Resources

| Resource | Used | Total | Status |
|----------|------|-------|--------|
| Disk | 30.2 GB | 74.8 GB | OK (40%) |
| Memory | 2.1 GB | 15.6 GB | OK (13.5%) |
| CPU Load | 0.20 | 8 cores | OK (2.5%) |
| Inodes | 282k | 4.8M | OK (6%) |

## Log Files

Located in `/var/log/lexi/`:
- `server_monitor.log` - System monitoring (updated 21:11:59)
- `deepseek_batch.log` - Batch processing (updated 20:51:45)
- `document_import.log` - Document imports (updated 18:53:13)
- `safe_import.log` - Safe mode imports (updated 18:51:58)
- `memgraph_lab_proxy_new.log` - Lab proxy logs

## Database Status

### PostgreSQL (Neon)
- **Status**: CONNECTED ✓
- **Version**: PostgreSQL 16.9
- **Tables**: 13 (users, tenants, chats, messages, artifacts, etc.)
- **Users**: 2 accounts
- **Connection**: SSL/TLS required

### Memgraph
- **Status**: ACCESSIBLE ✓
- **Documents**: Processing CAO legal documents
- **Import Rate**: 1300-1600 articles/second
- **Purpose**: Semantic indexing & relationships

## Document Processing Stats

- **Total Processed**: 45 documents
- **Successful**: 26 (57.8%)
- **Failed**: 19 (42.2%)
- **Articles Imported**: 211/216 (97.7%)
- **Processing Time**: 124.6 minutes (2.1 hours)
- **Performance**: 104 articles/hour

## Recommended Actions

### Short-term (1 hour)
1. Apply Priority 1 fixes above
2. Restart service: `systemctl restart lexi`
3. Test batch imports
4. Monitor logs for timeouts

### Medium-term (1-2 weeks)
1. Add Celery/Redis task queue
2. Implement memory pooling
3. Optimize DeepSeek API usage
4. Add progress tracking for imports

### Long-term (1+ month)
1. Implement embedding caching
2. Database optimization
3. Enhanced monitoring/alerting
4. Performance dashboards

## Troubleshooting Commands

```bash
# Check service status
systemctl status lexi

# View live logs
journalctl -u lexi -f

# Restart service
systemctl restart lexi

# Check worker memory
ps aux | grep gunicorn | head -10

# Test database connectivity
python3 -c "import socket; s=socket.socket(); s.connect(('127.0.0.1', 7687)); print('OK')"

# View gunicorn config
cat /var/www/lexi/gunicorn.conf.py | grep -E "timeout|workers|max_requests"

# Monitor system resources
watch -n 1 'free -h && df -h /'

# Check Memgraph status
curl -s localhost:7444 | head -20
```

## Contact & Support

For issues or questions:
1. Check the full report: `/var/www/lexi/HEALTH_CHECK_REPORT_2025-10-29.txt`
2. Review logs: `journalctl -u lexi -f`
3. Contact system administrator

---

*Report generated: 2025-10-29 21:12:32 UTC*  
*Last updated: 2025-10-29 21:13:00 UTC*  
*System: Linux (Hetzner Cloud) - Ubuntu*
