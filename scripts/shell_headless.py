#!/usr/bin/env python3

import os
import sys
import time
import argparse

# Ensure we can import main.py
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from main import start_shell_job, get_shell_job, SHELL_API_ENABLED


def run_headless(script: str, shell_path: str | None):
    # Force-enable shell API semantics for parity, but we call internals directly
    os.environ.setdefault('CEDARPY_SHELL_API_ENABLED', '1')

    job = start_shell_job(script=script, shell_path=shell_path)
    print(f"started job_id={job.id} log={job.log_path}")

    # Poll until done, streaming queued lines
    while True:
        # Flush any existing buffered lines
        while job.output_lines:
            line = job.output_lines.pop(0)
            sys.stdout.write(line)
            sys.stdout.flush()
        if job.status in ("finished", "error", "killed"):
            break
        time.sleep(0.2)

    print(f"status={job.status} return_code={job.return_code}")
    return 0 if (job.status == 'finished' and job.return_code == 0) else 1


def main():
    ap = argparse.ArgumentParser(description='Run CedarPy shell job headlessly')
    ap.add_argument('--shell', dest='shell_path', default=None, help='Path to shell (default: detect)')
    ap.add_argument('script', help='Script to run (quote as needed)')
    args = ap.parse_args()
    return run_headless(args.script, args.shell_path)


if __name__ == '__main__':
    raise SystemExit(main())
