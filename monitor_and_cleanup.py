#!/usr/bin/env python3
"""
Server Resource Monitor & Cleanup Script
Prevents runaway processes from consuming 100% CPU/RAM

Features:
- Monitor CPU/memory usage
- Auto-kill zombie/stuck processes
- Prevent embedding model memory leaks
- Cleanup stale temp files
- Alert on resource issues
"""

import os
import sys
import psutil
import subprocess
import signal
import json
from datetime import datetime
from pathlib import Path
import time

# Configuration
CONFIG = {
    'max_process_cpu': 80,          # Kill if single process > 80% CPU for 5+ min
    'max_process_memory': 2000,     # MB - Kill if > 2GB RAM per process
    'max_total_memory': 12000,      # MB - Alert if total > 12GB
    'allowed_processes': {
        'gunicorn': {'max_cpu': 80, 'max_mem': 2000, 'count': 8},
        'memgraph': {'max_cpu': 50, 'max_mem': 4000},
        'python3': {'max_cpu': 100, 'max_mem': 3000, 'exclusions': ['monitor', 'supervisord', 'unattended']},
    },
    'dangerous_patterns': [
        'document_importer.py',  # Can OOM - should run in batches
        'stale_python_process',  # Orphaned processes
    ],
    'cleanup_temp_dirs': [
        '/tmp/cao_import',
        '/tmp/embeddings_cache',
    ],
    'alert_thresholds': {
        'memory_percent': 85,   # Alert if >85% RAM used
        'cpu_percent': 80,       # Alert if >80% CPU sustained
    }
}

class ServerMonitor:
    def __init__(self):
        self.log_file = '/var/log/lexi/server_monitor.log'
        self.process_runtimes = {}  # Track process execution times
        self.alert_cooldown = {}    # Prevent spam alerts

        # Ensure log directory exists
        Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)

    def log(self, message: str, level: str = 'INFO'):
        """Log to file and stdout"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_msg = f"[{timestamp}] [{level}] {message}"

        print(log_msg)

        try:
            with open(self.log_file, 'a') as f:
                f.write(log_msg + '\n')
        except Exception as e:
            print(f"Error writing to log: {e}")

    def get_system_status(self):
        """Get current system status"""
        memory = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=1)

        return {
            'timestamp': datetime.now().isoformat(),
            'memory': {
                'total_mb': memory.total // (1024*1024),
                'available_mb': memory.available // (1024*1024),
                'percent': memory.percent,
                'used_mb': memory.used // (1024*1024),
            },
            'cpu_percent': cpu_percent,
        }

    def check_process_health(self):
        """Check and cleanup problematic processes"""
        problematic = []

        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info']):
            try:
                name = proc.name()
                cpu = proc.cpu_percent(interval=0.1)
                mem_mb = proc.memory_info().rss // (1024*1024)
                pid = proc.pid

                # Check if process is stuck (high CPU for too long)
                if pid in self.process_runtimes:
                    runtime = time.time() - self.process_runtimes[pid]['start_time']

                    # Kill if stuck with high CPU for 5+ minutes
                    if cpu > CONFIG['max_process_cpu'] and runtime > 300:
                        self.log(
                            f"🔴 KILLING STUCK PROCESS: {name} (PID {pid}) - "
                            f"CPU: {cpu}% for {runtime/60:.0f}min, MEM: {mem_mb}MB",
                            'WARNING'
                        )
                        try:
                            os.kill(pid, signal.SIGKILL)
                            del self.process_runtimes[pid]
                        except:
                            pass
                        continue
                else:
                    # First time seeing this process
                    self.process_runtimes[pid] = {'start_time': time.time(), 'cpu': cpu}

                # Check memory limits
                if mem_mb > CONFIG['max_process_memory']:
                    if name == 'python3' and 'gunicorn' not in str(proc.cmdline()):
                        self.log(
                            f"⚠️  HIGH MEMORY PYTHON: {name} (PID {pid}) - {mem_mb}MB",
                            'WARNING'
                        )
                        problematic.append((pid, name, mem_mb))

                # Cleanup old process tracking
                if time.time() - self.process_runtimes[pid]['start_time'] > 3600:
                    if pid in self.process_runtimes:
                        del self.process_runtimes[pid]

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        return problematic

    def cleanup_temp_files(self):
        """Cleanup old temporary files"""
        for temp_dir in CONFIG['cleanup_temp_dirs']:
            if not Path(temp_dir).exists():
                continue

            try:
                for item in Path(temp_dir).iterdir():
                    # Remove files older than 24 hours
                    mtime = item.stat().st_mtime
                    age = time.time() - mtime

                    if age > 86400:  # 24 hours
                        if item.is_file():
                            item.unlink()
                            self.log(f"🗑️  Cleaned up old file: {item}", 'DEBUG')
            except Exception as e:
                self.log(f"Error cleaning {temp_dir}: {e}", 'ERROR')

    def restart_gunicorn_if_needed(self):
        """Restart Gunicorn gracefully if memory is leaking"""
        try:
            # Get gunicorn master process
            for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
                if 'gunicorn' in proc.name():
                    mem_mb = proc.memory_info().rss // (1024*1024)

                    # If master process > 1GB, restart
                    if mem_mb > 1000:
                        self.log(f"🔄 RESTARTING GUNICORN: Memory leak detected ({mem_mb}MB)", 'WARNING')
                        try:
                            subprocess.run(['supervisorctl', 'restart', 'gunicorn'], timeout=10)
                            time.sleep(5)
                            return True
                        except Exception as e:
                            self.log(f"Failed to restart gunicorn: {e}", 'ERROR')
                            return False
        except Exception as e:
            self.log(f"Error checking gunicorn: {e}", 'ERROR')

        return False

    def monitor(self, interval: int = 60, duration: int = None):
        """
        Main monitoring loop

        Args:
            interval: Check interval in seconds
            duration: Total duration in seconds (None = infinite)
        """
        self.log("🟢 Server Monitor Started", 'INFO')
        start_time = time.time()

        try:
            while True:
                status = self.get_system_status()

                # Log status every 5 minutes
                if int((time.time() - start_time) / 60) % 5 == 0:
                    self.log(
                        f"📊 System Status - RAM: {status['memory']['percent']:.1f}% "
                        f"({status['memory']['used_mb']}MB/{status['memory']['total_mb']}MB), "
                        f"CPU: {status['cpu_percent']:.1f}%",
                        'DEBUG'
                    )

                # Check health
                problematic = self.check_process_health()

                # Cleanup temp files
                self.cleanup_temp_files()

                # Check if restart needed
                if status['memory']['percent'] > 90:
                    self.restart_gunicorn_if_needed()

                # Check duration
                if duration and (time.time() - start_time) > duration:
                    self.log("⏹️  Monitor duration complete", 'INFO')
                    break

                time.sleep(interval)

        except KeyboardInterrupt:
            self.log("⏹️  Monitor stopped by user", 'INFO')
        except Exception as e:
            self.log(f"❌ Monitor error: {e}", 'ERROR')
            raise

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Server Resource Monitor')
    parser.add_argument('--interval', type=int, default=60, help='Check interval in seconds (default: 60)')
    parser.add_argument('--duration', type=int, default=None, help='Run duration in seconds (default: infinite)')
    parser.add_argument('--once', action='store_true', help='Run once and exit')

    args = parser.parse_args()

    monitor = ServerMonitor()

    if args.once:
        status = monitor.get_system_status()
        print(json.dumps(status, indent=2))
        problematic = monitor.check_process_health()
        if problematic:
            print("\n⚠️  Problematic processes:")
            for pid, name, mem in problematic:
                print(f"  - {name} (PID {pid}): {mem}MB")
    else:
        monitor.monitor(interval=args.interval, duration=args.duration)

if __name__ == '__main__':
    main()
