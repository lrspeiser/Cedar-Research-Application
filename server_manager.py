#!/usr/bin/env python3
"""
Cedar Server Manager - Prevents multiple server instances
Provides clean start/stop/restart functionality with PID tracking
"""

import os
import sys
import signal
import subprocess
import time
import psutil
import socket
from pathlib import Path
from datetime import datetime
import argparse

class ServerManager:
    def __init__(self):
        self.project_dir = Path(__file__).parent.absolute()
        self.pid_file = self.project_dir / ".server.pid"
        self.lock_file = self.project_dir / ".server.lock"
        self.log_file = self.project_dir / "server.log"
        self.port = 8000
        self.python_cmd = ".venv/bin/python" if (self.project_dir / ".venv").exists() else "python3"
        
    def is_port_in_use(self, port):
        """Check if a port is already in use"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('', port))
                return False
            except:
                return True
    
    def get_process_using_port(self, port):
        """Get the PID of process using a specific port"""
        # Try using lsof first (more reliable on macOS)
        try:
            result = subprocess.run(
                ['lsof', '-i', f':{port}', '-t'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                # Return first PID that's listening
                for pid_str in pids:
                    try:
                        return int(pid_str)
                    except:
                        continue
        except:
            pass
        
        # Fallback to psutil
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    for conn in proc.net_connections(kind='inet'):
                        if conn.laddr.port == port and conn.status == 'LISTEN':
                            return proc.pid
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except:
            pass
        return None
    
    def read_pid_file(self):
        """Read the PID from the lock file"""
        if self.pid_file.exists():
            try:
                with open(self.pid_file, 'r') as f:
                    return int(f.read().strip())
            except:
                pass
        return None
    
    def write_pid_file(self, pid):
        """Write PID to the lock file"""
        with open(self.pid_file, 'w') as f:
            f.write(str(pid))
    
    def remove_pid_file(self):
        """Remove the PID file"""
        if self.pid_file.exists():
            self.pid_file.unlink()
            
    def is_process_running(self, pid):
        """Check if a process with given PID is running"""
        try:
            process = psutil.Process(pid)
            # Check if it's actually our Python server
            cmdline = ' '.join(process.cmdline())
            return 'main.py' in cmdline
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False
    
    def find_cedar_servers(self):
        """Find all running Cedar server processes"""
        cedar_pids = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'python' in proc.info['name'].lower() and 'main.py' in cmdline:
                    # Check if it's in our project directory
                    if str(self.project_dir) in cmdline or proc.cwd() == str(self.project_dir):
                        cedar_pids.append(proc.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return cedar_pids
    
    def stop_server(self, force=False):
        """Stop the server gracefully or forcefully"""
        stopped_any = False
        
        # Check PID file first
        pid = self.read_pid_file()
        if pid and self.is_process_running(pid):
            print(f"🛑 Stopping server (PID: {pid})...")
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(2)
                if self.is_process_running(pid) and force:
                    print(f"⚠️  Force killing server (PID: {pid})...")
                    os.kill(pid, signal.SIGKILL)
                stopped_any = True
            except ProcessLookupError:
                pass
            self.remove_pid_file()
        
        # Check for any process on port 8000
        port_pid = self.get_process_using_port(self.port)
        if port_pid:
            print(f"🛑 Found process on port {self.port} (PID: {port_pid}), stopping...")
            try:
                os.kill(port_pid, signal.SIGTERM)
                time.sleep(2)
                if force and self.get_process_using_port(self.port):
                    os.kill(port_pid, signal.SIGKILL)
                stopped_any = True
            except:
                pass
        
        # Find and stop all Cedar servers
        cedar_pids = self.find_cedar_servers()
        for pid in cedar_pids:
            print(f"🛑 Found Cedar server (PID: {pid}), stopping...")
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(1)
                if force and self.is_process_running(pid):
                    os.kill(pid, signal.SIGKILL)
                stopped_any = True
            except:
                pass
        
        if stopped_any:
            print("✅ Server(s) stopped")
        else:
            print("ℹ️  No server was running")
            
        # Clean up lock files
        self.remove_pid_file()
        if self.lock_file.exists():
            self.lock_file.unlink()
        
        return stopped_any
    
    def start_server(self, debug=False):
        """Start the server if not already running"""
        # Check if server is already running
        pid = self.read_pid_file()
        if pid and self.is_process_running(pid):
            print(f"⚠️  Server is already running (PID: {pid})")
            print(f"   Use 'python server_manager.py restart' to restart it")
            return False
        
        # Check if port is in use
        if self.is_port_in_use(self.port):
            port_pid = self.get_process_using_port(self.port)
            print(f"⚠️  Port {self.port} is already in use by process {port_pid}")
            print(f"   Use 'python server_manager.py stop' first or 'python server_manager.py restart'")
            return False
        
        # Check for lock file
        if self.lock_file.exists():
            print("⚠️  Lock file exists. Another instance may be starting.")
            print("   If you're sure no server is running, use 'python server_manager.py stop' first")
            return False
        
        # Create lock file
        self.lock_file.touch()
        
        try:
            print(f"🚀 Starting Cedar server on port {self.port}...")
            print(f"   Python: {self.python_cmd}")
            print(f"   Directory: {self.project_dir}")
            
            # Start the server
            if debug:
                # Run in foreground for debugging
                process = subprocess.Popen(
                    [self.python_cmd, "-u", "main.py"],
                    cwd=self.project_dir
                )
            else:
                # Run in background with logging
                with open(self.log_file, 'a') as log:
                    log.write(f"\n\n{'='*60}\n")
                    log.write(f"Server started at {datetime.now()}\n")
                    log.write(f"{'='*60}\n")
                    process = subprocess.Popen(
                        [self.python_cmd, "-u", "main.py"],
                        cwd=self.project_dir,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        start_new_session=True
                    )
            
            # Wait a bit to see if it starts successfully
            time.sleep(3)
            
            if process.poll() is not None:
                # Process ended already - likely an error
                print("❌ Server failed to start. Check server.log for details")
                self.lock_file.unlink()
                return False
            
            # Save PID
            self.write_pid_file(process.pid)
            
            # Verify server is responding
            time.sleep(2)
            if self.is_port_in_use(self.port):
                print(f"✅ Server started successfully (PID: {process.pid})")
                print(f"   URL: http://localhost:{self.port}")
                if not debug:
                    print(f"   Logs: tail -f {self.log_file}")
                return True
            else:
                print("⚠️  Server started but not responding on port")
                return False
                
        except Exception as e:
            print(f"❌ Failed to start server: {e}")
            if self.lock_file.exists():
                self.lock_file.unlink()
            return False
        finally:
            if self.lock_file.exists():
                self.lock_file.unlink()
    
    def restart_server(self):
        """Restart the server"""
        print("🔄 Restarting server...")
        self.stop_server()
        time.sleep(2)
        return self.start_server()
    
    def status(self):
        """Check server status"""
        pid = self.read_pid_file()
        
        print("Cedar Server Status")
        print("=" * 40)
        
        if pid and self.is_process_running(pid):
            print(f"✅ Server is running (PID: {pid})")
            try:
                process = psutil.Process(pid)
                print(f"   Started: {datetime.fromtimestamp(process.create_time())}")
                print(f"   Memory: {process.memory_info().rss / 1024 / 1024:.1f} MB")
                print(f"   CPU: {process.cpu_percent(interval=1)}%")
            except:
                pass
        else:
            print("❌ Server is not running (based on PID file)")
        
        # Check port
        if self.is_port_in_use(self.port):
            port_pid = self.get_process_using_port(self.port)
            if port_pid:
                print(f"ℹ️  Port {self.port} is in use by PID {port_pid}")
        else:
            print(f"ℹ️  Port {self.port} is free")
        
        # Check for any Cedar servers
        cedar_pids = self.find_cedar_servers()
        if cedar_pids:
            print(f"ℹ️  Found {len(cedar_pids)} Cedar server process(es): {cedar_pids}")
        
        print("=" * 40)

def main():
    parser = argparse.ArgumentParser(description='Cedar Server Manager')
    parser.add_argument('action', choices=['start', 'stop', 'restart', 'status'],
                      help='Action to perform')
    parser.add_argument('--force', '-f', action='store_true',
                      help='Force stop (kill -9) if graceful stop fails')
    parser.add_argument('--debug', '-d', action='store_true',
                      help='Run server in foreground with debug output')
    
    args = parser.parse_args()
    
    # Check for required dependencies
    try:
        import psutil
    except ImportError:
        print("❌ psutil is required. Install with: pip install psutil")
        sys.exit(1)
    
    manager = ServerManager()
    
    if args.action == 'start':
        success = manager.start_server(debug=args.debug)
        sys.exit(0 if success else 1)
    elif args.action == 'stop':
        manager.stop_server(force=args.force)
    elif args.action == 'restart':
        success = manager.restart_server()
        sys.exit(0 if success else 1)
    elif args.action == 'status':
        manager.status()

if __name__ == '__main__':
    main()