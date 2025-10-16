#!/usr/bin/env python3
"""
Git Autopush Runner - Scheduled Deployment Entry Point
Runs every 5 minutes to backup code to Git
"""
import subprocess
import sys
import os
from datetime import datetime

def run_git_autopush():
    """Execute git autopush script with logging"""
    print(f"{'='*60}")
    print(f"Git Autopush Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    script_path = os.path.join(os.path.dirname(__file__), 'git_autopush.sh')
    
    try:
        result = subprocess.run(
            ['bash', script_path],
            capture_output=True,
            text=True,
            timeout=60  # 1 minute timeout
        )
        
        print(result.stdout)
        
        if result.stderr:
            print("STDERR:", result.stderr, file=sys.stderr)
        
        if result.returncode != 0:
            print(f"\n❌ Git autopush failed with exit code {result.returncode}")
            sys.exit(result.returncode)
        
        print(f"\n{'='*60}")
        print(f"✅ Git Autopush Completed Successfully")
        print(f"{'='*60}")
        
    except subprocess.TimeoutExpired:
        print("❌ Git autopush timed out (>60 seconds)")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_git_autopush()
