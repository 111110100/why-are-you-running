#!/usr/bin/env python3
"""
wayr - Why Are You Running?

A utility that explains why processes, services, and ports exist on your system
by building a causal chain from supervisors to the running process.

Cross-platform: Works on Linux and macOS
"""

import argparse
import json
import os
import pwd
import re
import subprocess
import sys
import platform
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Tuple


VERSION = "1.0.9"

# Detect operating system
IS_MACOS = platform.system() == 'Darwin'
IS_LINUX = platform.system() == 'Linux'


@dataclass
class ProcessInfo:
    """Represents a process and its metadata."""
    pid: int
    name: str
    ppid: int
    user: str
    cmd: str
    start_time: datetime
    cwd: Optional[str] = None
    restart_count: int = 0
    rss_kb: int = 0

    # Source tracking
    source: Optional[str] = None
    source_detail: Optional[str] = None

    # Context
    git_repo: Optional[str] = None
    git_branch: Optional[str] = None
    container_name: Optional[str] = None
    container_image: Optional[str] = None
    listening_addresses: List[str] = field(default_factory=list)
    env_vars: Dict[str, str] = field(default_factory=dict)

    # Ancestry
    ancestry: List['ProcessInfo'] = field(default_factory=list)
    children: List['ProcessInfo'] = field(default_factory=list)


class Colors:
    """ANSI color codes."""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'

    @classmethod
    def disable(cls):
        """Disable all colors."""
        cls.RESET = ''
        cls.BOLD = ''
        cls.DIM = ''
        cls.RED = ''
        cls.GREEN = ''
        cls.YELLOW = ''
        cls.BLUE = ''
        cls.MAGENTA = ''
        cls.CYAN = ''


def run_command(cmd: List[str], check=False) -> Tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return e.returncode, e.stdout, e.stderr
    except FileNotFoundError:
        return 1, "", f"Command not found: {cmd[0]}"


def parse_elapsed_time_macos(etime: str) -> datetime:
    """Parse macOS ps elapsed time format to start_time."""
    # etime formats: [[dd-]hh:]mm:ss
    now = datetime.now()

    try:
        parts = etime.split('-')
        if len(parts) == 2:
            # Has days
            days = int(parts[0])
            time_part = parts[1]
        else:
            days = 0
            time_part = parts[0]

        time_components = time_part.split(':')
        if len(time_components) == 3:
            hours, minutes, seconds = map(int, time_components)
        elif len(time_components) == 2:
            hours = 0
            minutes, seconds = map(int, time_components)
        else:
            # Just seconds
            hours = 0
            minutes = 0
            seconds = int(time_components[0])

        total_seconds = days * 86400 + hours * 3600 + minutes * 60 + seconds
        return now - timedelta(seconds=total_seconds)
    except:
        return now


def get_process_info_macos(pid: int) -> Optional[ProcessInfo]:
    """Get process info on macOS using ps."""
    try:
        # Get basic process info
        rc, stdout, _ = run_command(['ps', '-p', str(pid), '-o', 'pid=,ppid=,user=,comm=,etime=,rss='])
        if rc != 0 or not stdout.strip():
            return None

        parts = stdout.strip().split(None, 5)
        if len(parts) < 6:
            return None

        pid_parsed = int(parts[0])
        ppid = int(parts[1])
        user = parts[2]
        name = os.path.basename(parts[3])
        etime = parts[4]
        rss_kb = int(parts[5])

        # Get full command line
        rc, cmd_out, _ = run_command(['ps', '-p', str(pid), '-o', 'command='])
        cmd = cmd_out.strip() if rc == 0 else name

        # Parse start time
        start_time = parse_elapsed_time_macos(etime)

        # Get working directory using lsof
        cwd = None
        rc, lsof_out, _ = run_command(['lsof', '-a', '-p', str(pid), '-d', 'cwd', '-Fn'])
        if rc == 0:
            for line in lsof_out.split('\n'):
                if line.startswith('n'):
                    cwd = line[1:]
                    break

        # Get environment variables
        env_vars = {}
        rc, env_out, _ = run_command(['ps', '-p', str(pid), '-E'])
        if rc == 0:
            for line in env_out.split('\n'):
                if '=' in line:
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        env_vars[parts[0].strip()] = parts[1].strip()

        return ProcessInfo(
            pid=pid_parsed,
            name=name,
            ppid=ppid,
            user=user,
            cmd=cmd,
            start_time=start_time,
            cwd=cwd,
            rss_kb=rss_kb,
            env_vars=env_vars
        )
    except Exception as e:
        return None


def get_process_info_linux(pid: int) -> Optional[ProcessInfo]:
    """Get process info on Linux using /proc."""
    try:
        # Read from /proc
        with open(f'/proc/{pid}/stat', 'r') as f:
            stat = f.read()

        # Parse stat - handle process names with spaces/parens
        match = re.match(r'^(\d+) \((.+?)\) (\S) (\d+)', stat)
        if not match:
            return None

        pid_parsed, name, state, ppid = match.groups()
        ppid = int(ppid)

        # Get command line
        try:
            with open(f'/proc/{pid}/cmdline', 'r') as f:
                cmdline = f.read().replace('\0', ' ').strip()
            if not cmdline:
                cmdline = f"[{name}]"
        except:
            cmdline = f"[{name}]"

        # Get user
        try:
            stat_info = os.stat(f'/proc/{pid}')
            user = pwd.getpwuid(stat_info.st_uid).pw_name
        except:
            user = "unknown"

        # Get start time
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.read().split()[0])

            with open(f'/proc/{pid}/stat', 'r') as f:
                stat_fields = f.read().split(')')[-1].split()

            # starttime is field 22 (index 19 after the split)
            starttime_ticks = int(stat_fields[19])
            ticks_per_second = os.sysconf(os.sysconf_names['SC_CLK_TCK'])
            process_age = uptime_seconds - (starttime_ticks / ticks_per_second)
            start_time = datetime.now() - timedelta(seconds=process_age)
        except:
            start_time = datetime.now()

        # Get memory usage (RSS in KB)
        rss_kb = 0
        try:
            with open(f'/proc/{pid}/status', 'r') as f:
                for line in f:
                    if line.startswith('VmRSS:'):
                        rss_kb = int(line.split()[1])
                        break
        except:
            pass

        # Get working directory
        cwd = None
        try:
            cwd = os.readlink(f'/proc/{pid}/cwd')
        except:
            pass

        # Get environment variables
        env_vars = {}
        try:
            with open(f'/proc/{pid}/environ', 'r') as f:
                env_data = f.read()
                for item in env_data.split('\0'):
                    if '=' in item:
                        key, value = item.split('=', 1)
                        env_vars[key] = value
        except:
            pass

        return ProcessInfo(
            pid=pid,
            name=name,
            ppid=ppid,
            user=user,
            cmd=cmdline,
            start_time=start_time,
            cwd=cwd,
            rss_kb=rss_kb,
            env_vars=env_vars
        )
    except:
        return None


def get_process_info(pid: int) -> Optional[ProcessInfo]:
    """Get detailed process information for a PID (OS-aware)."""
    if IS_MACOS:
        return get_process_info_macos(pid)
    elif IS_LINUX:
        return get_process_info_linux(pid)
    else:
        # Try macOS method for other Unix-like systems
        return get_process_info_macos(pid)


def find_processes_by_name(name: str, exact: bool = False) -> List[ProcessInfo]:
    """Find all processes matching a name."""
    matches = []
    own_pid = os.getpid()

    # Use ps to get all process IDs
    if IS_MACOS:
        rc, stdout, _ = run_command(['ps', '-A', '-o', 'pid='])
    else:
        rc, stdout, _ = run_command(['ps', '-eo', 'pid='])

    if rc != 0:
        return matches

    pids = []
    for line in stdout.strip().split('\n'):
        try:
            pid = int(line.strip())
            if pid != own_pid:
                pids.append(pid)
        except:
            continue

    for pid in pids:
        proc_info = get_process_info(pid)
        if not proc_info:
            continue

        # Skip our own wayr process
        if 'wayr' in proc_info.cmd and name in proc_info.cmd:
            continue

        if exact:
            if proc_info.name == name:
                matches.append(proc_info)
        else:
            # Fuzzy matching
            if name.lower() in proc_info.name.lower():
                matches.append(proc_info)
            elif name.lower() in proc_info.cmd.lower():
                # Exclude if it's our search argument
                cmd_parts = proc_info.cmd.split()
                is_our_arg = False
                for i, part in enumerate(cmd_parts):
                    if 'wayr' in part and i + 1 < len(cmd_parts) and cmd_parts[i + 1] == name:
                        is_our_arg = True
                        break
                if not is_our_arg:
                    matches.append(proc_info)

    return matches


def find_process_by_port(port: int) -> List[ProcessInfo]:
    """Find processes listening on a port."""
    processes = []

    # Try lsof (works on both macOS and Linux)
    rc, stdout, _ = run_command(['lsof', '-i', f':{port}', '-sTCP:LISTEN', '-t'])
    if rc == 0:
        for pid_str in stdout.strip().split('\n'):
            if pid_str:
                try:
                    pid = int(pid_str)
                    proc_info = get_process_info(pid)
                    if proc_info:
                        # Get listening address
                        rc2, addr_out, _ = run_command(['lsof', '-i', f':{port}', '-sTCP:LISTEN', '-a', '-p', str(pid)])
                        if rc2 == 0:
                            for line in addr_out.split('\n'):
                                if 'LISTEN' in line:
                                    parts = line.split()
                                    if len(parts) >= 9:
                                        addr = parts[8]
                                        if addr not in proc_info.listening_addresses:
                                            proc_info.listening_addresses.append(addr)
                        if proc_info not in processes:
                            processes.append(proc_info)
                except:
                    pass

    # Linux fallback to /proc/net/tcp
    if not processes and IS_LINUX:
        processes.extend(find_process_by_port_linux_proc(port))

    return processes


def find_process_by_port_linux_proc(port: int) -> List[ProcessInfo]:
    """Find processes by port using /proc/net/tcp* - Linux only."""
    processes = []
    port_hex = f"{port:04X}"

    for net_file in ['/proc/net/tcp', '/proc/net/tcp6']:
        try:
            with open(net_file, 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) < 10:
                        continue

                    local_addr = parts[1]
                    state = parts[3]
                    inode = parts[9]

                    if state != '0A':  # Not LISTEN
                        continue

                    if ':' in local_addr:
                        addr_port = local_addr.split(':')[1]
                        if addr_port.upper() == port_hex.upper():
                            proc_info = find_process_by_socket_inode_linux(inode)
                            if proc_info:
                                addr_ip = local_addr.split(':')[0]
                                if len(addr_ip) == 8:  # IPv4
                                    ip_parts = [str(int(addr_ip[i:i+2], 16)) for i in range(6, -1, -2)]
                                    ip_str = '.'.join(ip_parts)
                                else:
                                    ip_str = addr_ip
                                proc_info.listening_addresses.append(f"{ip_str}:{port}")
                                if proc_info not in processes:
                                    processes.append(proc_info)
        except:
            continue

    return processes


def find_process_by_socket_inode_linux(inode: str) -> Optional[ProcessInfo]:
    """Find process that owns a socket inode - Linux only."""
    try:
        proc_dir = Path('/proc')
        for pid_dir in proc_dir.iterdir():
            if not pid_dir.is_dir() or not pid_dir.name.isdigit():
                continue

            fd_dir = pid_dir / 'fd'
            if not fd_dir.exists():
                continue

            try:
                for fd in fd_dir.iterdir():
                    try:
                        link = os.readlink(str(fd))
                        if f'socket:[{inode}]' in link:
                            return get_process_info(int(pid_dir.name))
                    except:
                        continue
            except:
                continue
    except:
        pass

    return None


def build_ancestry(proc: ProcessInfo) -> List[ProcessInfo]:
    """Build the ancestry chain from init to this process."""
    ancestry = []
    current_pid = proc.ppid

    while current_pid > 0:
        parent = get_process_info(current_pid)
        if not parent:
            break
        ancestry.insert(0, parent)
        current_pid = parent.ppid

        # Safety: stop at init or max depth
        if current_pid == 1 or len(ancestry) > 20:
            break

    return ancestry


def build_process_tree(proc: ProcessInfo) -> None:
    """Build children tree for a process - non-recursive, efficient version."""
    # Get all processes in a single ps call
    if IS_MACOS:
        rc, stdout, _ = run_command(['ps', '-A', '-o', 'pid=,ppid='])
    else:
        rc, stdout, _ = run_command(['ps', '-eo', 'pid=,ppid='])

    if rc != 0:
        return

    # Build a map of pid -> ppid for all processes
    pid_to_ppid = {}
    for line in stdout.strip().split('\n'):
        try:
            parts = line.strip().split()
            if len(parts) >= 2:
                pid = int(parts[0])
                ppid = int(parts[1])
                pid_to_ppid[pid] = ppid
        except:
            continue

    # Build a map of ppid -> [child pids] for quick lookup
    ppid_to_children = {}
    for pid, ppid in pid_to_ppid.items():
        if ppid not in ppid_to_children:
            ppid_to_children[ppid] = []
        ppid_to_children[ppid].append(pid)

    # Cache for ProcessInfo objects to avoid recreating them
    process_cache = {proc.pid: proc}

    # Build the tree using breadth-first approach with a queue
    # Start with the root process
    queue = [proc]

    while queue:
        current = queue.pop(0)

        # Get all children of current process
        child_pids = ppid_to_children.get(current.pid, [])

        for child_pid in child_pids:
            # Get or create ProcessInfo for this child
            if child_pid not in process_cache:
                child_info = get_process_info(child_pid)
                if child_info:
                    process_cache[child_pid] = child_info
                else:
                    continue
            else:
                child_info = process_cache[child_pid]

            # Add to parent's children
            if child_info not in current.children:
                current.children.append(child_info)
                # Add to queue for processing its children
                queue.append(child_info)


def detect_source(proc: ProcessInfo) -> None:
    """Detect the primary source/supervisor for a process."""
    # Check ancestry for known supervisors
    for ancestor in reversed(proc.ancestry):
        # systemd (Linux)
        if ancestor.name == 'systemd' and ancestor.pid != 1:
            proc.source = "systemd"
            if IS_LINUX:
                rc, stdout, _ = run_command(['systemctl', 'status', str(proc.pid)])
                if rc == 0:
                    for line in stdout.splitlines():
                        if '.service' in line or '.socket' in line:
                            match = re.search(r'([a-zA-Z0-9._-]+\.(service|socket|timer))', line)
                            if match:
                                proc.source_detail = match.group(1)
                                break
            return

        # launchd (macOS)
        if ancestor.name == 'launchd':
            proc.source = "launchd"
            return

        # Docker
        if 'docker' in ancestor.name or 'containerd' in ancestor.name:
            proc.source = "docker"
            rc, stdout, _ = run_command(['docker', 'ps', '--no-trunc'])
            if rc == 0:
                for line in stdout.splitlines():
                    if str(proc.pid) in line:
                        parts = line.split()
                        if len(parts) > 1:
                            proc.container_name = parts[-1]
                            proc.container_image = parts[1]
                            proc.source_detail = proc.container_name
            return

        # PM2
        if 'PM2' in ancestor.cmd or 'pm2' in ancestor.name:
            proc.source = "pm2"
            return

        # Supervisor
        if 'supervisor' in ancestor.name:
            proc.source = "supervisor"
            return

        # Cron
        if ancestor.name == 'cron' or 'CRON' in ancestor.cmd:
            proc.source = "cron"
            return

        # Shell
        if ancestor.name in ['bash', 'zsh', 'fish', 'sh', 'dash', 'tcsh', 'csh']:
            proc.source = "interactive shell"
            proc.source_detail = ancestor.name
            return

    # Default
    if not proc.source:
        proc.source = "unknown"


def detect_git_context(proc: ProcessInfo) -> None:
    """Detect git repository context."""
    if not proc.cwd:
        return

    try:
        cwd = Path(proc.cwd)
        current = cwd
        for _ in range(10):
            git_dir = current / '.git'
            if git_dir.exists():
                proc.git_repo = current.name
                head_file = git_dir / 'HEAD'
                if head_file.exists():
                    with open(head_file, 'r') as f:
                        head_content = f.read().strip()
                        if head_content.startswith('ref: refs/heads/'):
                            proc.git_branch = head_content.replace('ref: refs/heads/', '')
                break

            if current == current.parent:
                break
            current = current.parent
    except:
        pass


def detect_listening_ports(proc: ProcessInfo) -> None:
    """Detect ports the process is listening on."""
    if proc.listening_addresses:
        return

    try:
        # Use lsof (cross-platform)
        rc, stdout, _ = run_command(['lsof', '-a', '-p', str(proc.pid), '-iTCP', '-sTCP:LISTEN'])
        if rc == 0:
            for line in stdout.splitlines():
                parts = line.split()
                if len(parts) >= 9 and 'LISTEN' in line:
                    addr = parts[8]
                    if addr not in proc.listening_addresses:
                        proc.listening_addresses.append(addr)

        # Linux fallback
        if not proc.listening_addresses and IS_LINUX:
            detect_listening_ports_linux_proc(proc)
    except:
        pass


def detect_listening_ports_linux_proc(proc: ProcessInfo) -> None:
    """Detect listening ports using /proc - Linux only."""
    try:
        fd_dir = Path(f'/proc/{proc.pid}/fd')
        if not fd_dir.exists():
            return

        socket_inodes = set()
        for fd in fd_dir.iterdir():
            try:
                link = os.readlink(str(fd))
                if link.startswith('socket:['):
                    inode = link[8:-1]
                    socket_inodes.add(inode)
            except:
                continue

        if not socket_inodes:
            return

        for net_file in ['/proc/net/tcp', '/proc/net/tcp6']:
            try:
                with open(net_file, 'r') as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) < 10:
                            continue

                        local_addr = parts[1]
                        state = parts[3]
                        inode = parts[9]

                        if state == '0A' and inode in socket_inodes:
                            if ':' in local_addr:
                                addr_hex, port_hex = local_addr.split(':')
                                port = int(port_hex, 16)

                                if len(addr_hex) == 8:  # IPv4
                                    ip_parts = [str(int(addr_hex[i:i+2], 16)) for i in range(6, -1, -2)]
                                    ip_str = '.'.join(ip_parts)
                                else:
                                    ip_str = f"[{addr_hex}]"

                                proc.listening_addresses.append(f"{ip_str}:{port}")
            except:
                continue
    except:
        pass


def get_warnings(proc: ProcessInfo) -> List[str]:
    """Generate warnings for a process."""
    warnings = []

    # Running as root
    if proc.user == 'root' and proc.pid != 1:
        warnings.append("Process is running as root")

    # Public bind
    for addr in proc.listening_addresses:
        if addr.startswith('0.0.0.0:') or addr.startswith('*:') or addr.startswith(':::'):
            warnings.append(f"Listening on public interface ({addr})")
            break

    # High restart count
    if proc.restart_count > 5:
        warnings.append(f"Process has restarted {proc.restart_count} times")

    # High memory
    if proc.rss_kb > 1024 * 1024:  # > 1GB
        warnings.append(f"High memory usage ({proc.rss_kb // 1024} MB)")

    # Long running
    uptime = datetime.now() - proc.start_time
    if uptime.days > 90:
        warnings.append(f"Process has been running for {uptime.days} days")

    return warnings


def get_command_description(cmd: str, debug: bool = False) -> Optional[str]:
    """Get the description of a command from its man page NAME section."""
    # Extract the base command name (first word, without path)
    cmd_parts = cmd.strip().split()
    if not cmd_parts:
        return None

    base_cmd = os.path.basename(cmd_parts[0])

    # Skip interpreters and shells - get the actual script name instead
    interpreters = ['python', 'python2', 'python3', 'node', 'ruby', 'perl',
                    'bash', 'sh', 'zsh', 'fish', 'java', 'php']
    if base_cmd in interpreters and len(cmd_parts) > 1:
        # Try to get description of the script instead
        script_name = os.path.basename(cmd_parts[1])
        # Remove extensions
        script_name = script_name.split('.')[0]
        base_cmd = script_name

    if debug:
        print(f"\n{Colors.YELLOW}[DEBUG] Trying to get man page for: {base_cmd}{Colors.RESET}")

    try:
        # First, try to get the path to the man page file using man -w
        # This allows us to parse the raw source file which is more reliable
        rc_path, man_path, _ = run_command(['man', '-w', base_cmd])
        if rc_path == 0 and man_path.strip():
            man_file_path = man_path.strip()
            if debug:
                print(f"{Colors.CYAN}[DEBUG] Found man page file at: {man_file_path}{Colors.RESET}")

            # Try to read the raw man page file
            try:
                with open(man_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    raw_content = f.read()

                if debug:
                    print(f"{Colors.GREEN}[DEBUG] Read raw man page file ({len(raw_content)} chars){Colors.RESET}")

                # Parse the raw file directly (more reliable than formatted output)

                # 1. Try BSD mdoc format (.Nd macro)
                for line in raw_content.split('\n'):
                    if line.strip().startswith('.Nd '):
                        desc = line.strip()[4:].strip()
                        if desc:
                            if desc[0].islower():
                                desc = desc[0].upper() + desc[1:]
                            if debug:
                                print(f"{Colors.GREEN}[DEBUG] Found .Nd macro in raw file: {repr(desc)}{Colors.RESET}")
                            return desc

                if debug:
                    print(f"{Colors.YELLOW}[DEBUG] No .Nd macro in raw file, trying troff format{Colors.RESET}")

                # 2. Try troff/groff format (.SH NAME section)
                # Common patterns:
                # .SH "NAME"  or  .SH NAME
                # followed by lines like:
                # npm - javascript package manager
                # or with formatting:
                # \fBnpm\fR - javascript package manager
                # or:
                # .LP
                # btop - Resource monitor...

                lines = raw_content.split('\n')
                in_name_section = False
                name_content_lines = []

                for i, line in enumerate(lines):
                    stripped = line.strip()

                    # Detect .SH NAME section
                    if re.match(r'^\.SH\s+"?NAME"?\s*$', stripped, re.IGNORECASE):
                        in_name_section = True
                        if debug:
                            print(f"{Colors.CYAN}[DEBUG] Found .SH NAME section at line {i}{Colors.RESET}")
                        continue

                    # Exit NAME section when we hit another .SH
                    if in_name_section and stripped.startswith('.SH '):
                        if debug:
                            print(f"{Colors.CYAN}[DEBUG] Exiting NAME section at line {i}{Colors.RESET}")
                        break

                    # Collect content in NAME section
                    if in_name_section:
                        # Skip common troff directives that don't contain description
                        if stripped.startswith('.LP') or stripped.startswith('.PP'):
                            continue
                        # Skip empty lines
                        if not stripped:
                            continue
                        # Skip lines that are only troff commands
                        if stripped.startswith('.') and len(stripped.split()) <= 2:
                            continue

                        # Add non-directive lines
                        if not stripped.startswith('.'):
                            name_content_lines.append(stripped)
                        # Also check for inline text after directives
                        elif ' ' in stripped and not stripped.startswith('.SH'):
                            # Lines like ".B name - description"
                            content = stripped.split(None, 1)
                            if len(content) > 1:
                                name_content_lines.append(content[1])

                if name_content_lines:
                    # Join and clean up troff formatting
                    description = ' '.join(name_content_lines)

                    # Remove troff formatting codes (comprehensive cleanup)
                    # Font changes: \fB (bold), \fI (italic), \fR (roman), \fP (previous)
                    description = re.sub(r'\\f.', '', description)
                    # Two-char font codes: \f(XX
                    description = re.sub(r'\\f\([A-Z]{2}\)', '', description)
                    # Special characters
                    description = description.replace('\\-', '-')  # minus/hyphen
                    description = description.replace('\\ ', ' ')  # non-breaking space
                    description = description.replace('\\&', '')   # zero-width space
                    description = description.replace('\\(em', '—')  # em-dash
                    description = description.replace('\\(en', '–')  # en-dash
                    # Remove any remaining backslash escapes (be conservative)
                    description = re.sub(r'\\(.)', r'\1', description)

                    # Clean up whitespace
                    description = ' '.join(description.split())

                    if debug:
                        print(f"{Colors.MAGENTA}[DEBUG] Raw troff NAME content: {repr(description)}{Colors.RESET}")

                    # Try to extract after dash
                    for dash in ['–', '—', '−', '-']:
                        if dash in description:
                            parts = description.split(dash, 1)
                            if len(parts) == 2:
                                desc = parts[1].strip()
                                if len(desc) >= 5:
                                    if desc[0].islower():
                                        desc = desc[0].upper() + desc[1:]
                                    if debug:
                                        print(f"{Colors.GREEN}[DEBUG] Extracted from troff NAME: {repr(desc)}{Colors.RESET}")
                                    return desc

                    # If no dash, return whole description if reasonable
                    if 10 <= len(description) <= 200:
                        if debug:
                            print(f"{Colors.GREEN}[DEBUG] Returning whole troff NAME content: {repr(description)}{Colors.RESET}")
                        return description

                if debug:
                    print(f"{Colors.YELLOW}[DEBUG] No troff NAME content found, will try formatted output{Colors.RESET}")

            except Exception as e:
                if debug:
                    print(f"{Colors.YELLOW}[DEBUG] Could not read raw man file: {e}{Colors.RESET}")
                # Fall through to use formatted man output

        # Try to get man page (formatted output as fallback)
        rc, stdout, _ = run_command(['man', base_cmd])
        if rc != 0:
            if debug:
                print(f"{Colors.RED}[DEBUG] man command failed (rc={rc}){Colors.RESET}")
            return None

        if debug:
            print(f"{Colors.GREEN}[DEBUG] Got man page formatted output ({len(stdout)} chars){Colors.RESET}")

        # First, try BSD mdoc format (.Nd macro)
        # This is common on macOS and BSD systems
        for line in stdout.split('\n'):
            # Look for .Nd macro (name description)
            if line.strip().startswith('.Nd '):
                desc = line.strip()[4:].strip()  # Remove '.Nd ' prefix
                if desc:
                    # Capitalize first letter if needed
                    if desc[0].islower():
                        desc = desc[0].upper() + desc[1:]
                    if debug:
                        print(f"{Colors.GREEN}[DEBUG] Found .Nd macro: {repr(desc)}{Colors.RESET}")
                    return desc

        if debug:
            print(f"{Colors.YELLOW}[DEBUG] No .Nd macro found, trying standard NAME section{Colors.RESET}")

        # Parse the NAME section - handle multiple formats
        lines = stdout.split('\n')
        in_name_section = False
        description_lines = []

        for i, line in enumerate(lines):
            # Detect NAME section header (case-insensitive, handles various formats)
            stripped = line.strip()

            # Check for NAME header in various formats:
            # "NAME", "Name", "name"
            # May have leading spaces/tabs
            if re.match(r'^NAME\s*$', stripped, re.IGNORECASE):
                in_name_section = True
                if debug:
                    print(f"{Colors.CYAN}[DEBUG] Found NAME section at line {i}{Colors.RESET}")
                continue

            # Exit NAME section when we hit another section header
            # Section headers are usually all caps or Title Case
            if in_name_section:
                # Check if this is a new section (all uppercase, at least 2 chars)
                if re.match(r'^[A-Z][A-Z\s]{1,}$', stripped) and len(stripped) >= 2:
                    # Make sure it's not "NAME" itself
                    if not re.match(r'^NAME\s*$', stripped, re.IGNORECASE):
                        if debug:
                            print(f"{Colors.CYAN}[DEBUG] Exiting NAME section at line {i} (found: {stripped}){Colors.RESET}")
                        break

            # Collect description lines in NAME section
            # Skip lines that are mdoc macros (.Nm, .Nd, etc.)
            if in_name_section and line.strip() and not line.strip().startswith('.'):
                description_lines.append(line.strip())

        if not description_lines:
            if debug:
                print(f"{Colors.RED}[DEBUG] No description lines found in NAME section{Colors.RESET}")
            return None

        # Join description lines and clean up
        description = ' '.join(description_lines)

        if debug:
            print(f"{Colors.MAGENTA}[DEBUG] Raw NAME content: {repr(description)}{Colors.RESET}")

        # Remove excessive whitespace
        description = ' '.join(description.split())

        if debug:
            print(f"{Colors.MAGENTA}[DEBUG] Cleaned description: {repr(description)}{Colors.RESET}")

        # Try to extract the part after various dash types
        # Common formats:
        # "command – description"
        # "command - description"
        # "command — description"
        # "command, alias1, alias2 - description"
        # "command(1) - description"

        # Try different dash styles (in order of preference)
        for dash in ['–', '—', '−', '-']:
            if dash in description:
                parts = description.split(dash, 1)
                if len(parts) == 2:
                    desc = parts[1].strip()

                    if debug:
                        print(f"{Colors.CYAN}[DEBUG] Found dash '{dash}', extracted: {repr(desc)}{Colors.RESET}")

                    # Remove any trailing periods
                    desc = desc.rstrip('.')

                    # Capitalize first letter if not already
                    if desc and desc[0].islower():
                        desc = desc[0].upper() + desc[1:]

                    # If description is too short (< 5 chars), might be parsing error
                    if len(desc) >= 5:
                        if debug:
                            print(f"{Colors.GREEN}[DEBUG] Returning: {repr(desc)}{Colors.RESET}")
                        return desc
                    elif debug:
                        print(f"{Colors.YELLOW}[DEBUG] Description too short ({len(desc)} chars), skipping{Colors.RESET}")

        # If no dash found but we have a description, try other patterns
        if description:
            if debug:
                print(f"{Colors.YELLOW}[DEBUG] No dash found, trying alternative parsing{Colors.RESET}")

            # Sometimes format is just: "commandname description here"
            # Try to remove the command name from the beginning
            words = description.split(None, 1)
            if len(words) >= 2:
                # Check if first word looks like command name (has alphanumeric, maybe with punctuation)
                first_word = words[0].rstrip(',:;()[]')
                if first_word.lower() == base_cmd.lower() or first_word == base_cmd:
                    # Return everything after the command name
                    desc = words[1].strip().rstrip('.')
                    if len(desc) >= 5:
                        if desc[0].islower():
                            desc = desc[0].upper() + desc[1:]
                        if debug:
                            print(f"{Colors.GREEN}[DEBUG] Extracted after command name: {repr(desc)}{Colors.RESET}")
                        return desc

            # Last resort: return the whole description if it's reasonable length
            if 10 <= len(description) <= 200:
                if debug:
                    print(f"{Colors.GREEN}[DEBUG] Returning whole description: {repr(description)}{Colors.RESET}")
                return description

        if debug:
            print(f"{Colors.RED}[DEBUG] Could not extract usable description{Colors.RESET}")

    except Exception as e:
        if debug:
            print(f"{Colors.RED}[DEBUG] Exception: {e}{Colors.RESET}")
        # Silently ignore errors in non-debug mode
        pass

    return None
    """Get the description of a command from its man page NAME section."""
    # Extract the base command name (first word, without path)
    cmd_parts = cmd.strip().split()
    if not cmd_parts:
        return None

    base_cmd = os.path.basename(cmd_parts[0])

    # Skip interpreters and shells - get the actual script name instead
    interpreters = ['python', 'python2', 'python3', 'node', 'ruby', 'perl',
                    'bash', 'sh', 'zsh', 'fish', 'java', 'php']
    if base_cmd in interpreters and len(cmd_parts) > 1:
        # Try to get description of the script instead
        script_name = os.path.basename(cmd_parts[1])
        # Remove extensions
        script_name = script_name.split('.')[0]
        base_cmd = script_name

    try:
        # Try to get man page
        rc, stdout, _ = run_command(['man', base_cmd])
        if rc != 0:
            return None

        # Parse the NAME section - handle multiple formats
        lines = stdout.split('\n')
        in_name_section = False
        description_lines = []

        for i, line in enumerate(lines):
            # Detect NAME section header (case-insensitive, handles various formats)
            stripped = line.strip()

            # Check for NAME header in various formats:
            # "NAME", "Name", "name"
            # May have leading spaces/tabs
            if re.match(r'^NAME\s*$', stripped, re.IGNORECASE):
                in_name_section = True
                continue

            # Exit NAME section when we hit another section header
            # Section headers are usually all caps or Title Case
            if in_name_section:
                # Check if this is a new section (all uppercase, at least 2 chars)
                if re.match(r'^[A-Z][A-Z\s]{1,}$', stripped) and len(stripped) >= 2:
                    # Make sure it's not "NAME" itself
                    if not re.match(r'^NAME\s*$', stripped, re.IGNORECASE):
                        break

            # Collect description lines in NAME section
            if in_name_section and line.strip():
                description_lines.append(line.strip())

        if not description_lines:
            return None

        # Join description lines and clean up
        description = ' '.join(description_lines)

        # Remove excessive whitespace
        description = ' '.join(description.split())

        # Try to extract the part after various dash types
        # Common formats:
        # "command – description"
        # "command - description"
        # "command — description"
        # "command, alias1, alias2 - description"
        # "command(1) - description"

        # Try different dash styles (in order of preference)
        for dash in ['–', '—', '−', '-']:
            if dash in description:
                parts = description.split(dash, 1)
                if len(parts) == 2:
                    desc = parts[1].strip()

                    # Remove any trailing periods
                    desc = desc.rstrip('.')

                    # Capitalize first letter if not already
                    if desc and desc[0].islower():
                        desc = desc[0].upper() + desc[1:]

                    # If description is too short (< 5 chars), might be parsing error
                    if len(desc) >= 5:
                        return desc

        # If no dash found but we have a description, try other patterns
        if description:
            # Sometimes format is just: "commandname description here"
            # Try to remove the command name from the beginning
            words = description.split(None, 1)
            if len(words) >= 2:
                # Check if first word looks like command name (has alphanumeric, maybe with punctuation)
                first_word = words[0].rstrip(',:;()[]')
                if first_word.lower() == base_cmd.lower() or first_word == base_cmd:
                    # Return everything after the command name
                    desc = words[1].strip().rstrip('.')
                    if len(desc) >= 5:
                        if desc[0].islower():
                            desc = desc[0].upper() + desc[1:]
                        return desc

            # Last resort: return the whole description if it's reasonable length
            if 10 <= len(description) <= 200:
                return description

    except Exception as e:
        # Silently ignore errors
        pass

    return None


def format_time_ago(dt: datetime) -> str:
    """Format a datetime as 'X time ago'."""
    delta = datetime.now() - dt

    if delta.days > 0:
        return f"{delta.days} day{'s' if delta.days != 1 else ''} ago"
    elif delta.seconds >= 3600:
        hours = delta.seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif delta.seconds >= 60:
        minutes = delta.seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    else:
        return f"{delta.seconds} second{'s' if delta.seconds != 1 else ''} ago"


def print_process_info(proc: ProcessInfo, args):
    """Print full process information."""
    c = Colors

    print(f"{c.BOLD}Target{c.RESET}      : {proc.name}")
    print(f"{c.BOLD}Process{c.RESET}     : {c.CYAN}{proc.name}{c.RESET} (pid {c.YELLOW}{proc.pid}{c.RESET})")
    print(f"{c.BOLD}User{c.RESET}        : {proc.user}")
    print(f"{c.BOLD}Command{c.RESET}     : {c.DIM}{proc.cmd}{c.RESET}")

    # Get command description from man page
    debug_man = getattr(args, 'debug_man', False)
    cmd_desc = get_command_description(proc.cmd, debug=debug_man)
    if cmd_desc:
        print(f"{c.BOLD}What it is{c.RESET}  : {cmd_desc}")

    print(f"{c.BOLD}Started{c.RESET}     : {format_time_ago(proc.start_time)} ({proc.start_time.strftime('%a %Y-%m-%d %H:%M:%S')})")

    if proc.restart_count > 0:
        print(f"{c.BOLD}Restarts{c.RESET}    : {proc.restart_count}")

    # Why it exists
    print(f"{c.BOLD}Why It Exists{c.RESET} :")
    ancestry_str = " → ".join([f"{p.name} (pid {p.pid})" for p in proc.ancestry + [proc]])
    print(f"  {c.GREEN}{ancestry_str}{c.RESET}")

    # Source
    if proc.source:
        source_display = proc.source
        if proc.source_detail:
            source_display += f" ({proc.source_detail})"
        print(f"{c.BOLD}Source{c.RESET}      : {c.MAGENTA}{source_display}{c.RESET}")

    # Context
    if proc.cwd:
        print(f"{c.BOLD}Working Dir{c.RESET} : {proc.cwd}")

    if proc.git_repo:
        git_info = proc.git_repo
        if proc.git_branch:
            git_info += f" ({proc.git_branch})"
        print(f"{c.BOLD}Git Repo{c.RESET}    : {git_info}")

    if proc.container_name:
        print(f"{c.BOLD}Container{c.RESET}   : {proc.container_name}")
        if proc.container_image:
            print(f"{c.BOLD}Image{c.RESET}       : {proc.container_image}")

    if proc.listening_addresses:
        print(f"{c.BOLD}Listening{c.RESET}   : {', '.join(proc.listening_addresses)}")

    # Extended info
    if args.verbose:
        print(f"\n{c.BOLD}Extended Info:{c.RESET}")
        print(f"  Memory (RSS): {proc.rss_kb // 1024} MB")
        print(f"  PPID: {proc.ppid}")

    # Environment variables
    if args.env and proc.env_vars:
        print(f"\n{c.BOLD}Environment Variables:{c.RESET}")
        for key, value in sorted(proc.env_vars.items()):
            print(f"  {key}={value}")

    # Warnings
    warnings = get_warnings(proc)
    if warnings and not args.warnings:
        print(f"\n{c.BOLD}{c.YELLOW}Warnings:{c.RESET}")
        for warning in warnings:
            print(f"  {c.YELLOW}⚠{c.RESET}  {warning}")


def print_short(proc: ProcessInfo):
    """Print short ancestry format."""
    ancestry_str = " → ".join([f"{p.name} (pid {p.pid})" for p in proc.ancestry + [proc]])
    print(ancestry_str)


def print_tree(proc: ProcessInfo, prefix: str = "", is_last: bool = True, is_root: bool = True):
    """Print process tree recursively in pstree format."""
    c = Colors

    # Print current process
    if is_root:
        # Root process - no connector
        print(f"{c.CYAN}{proc.name}{c.RESET} (pid {c.YELLOW}{proc.pid}{c.RESET})")
        child_prefix = ""
    else:
        # Child process - with connector
        connector = "└─" if is_last else "├─"
        print(f"{prefix}{connector}{c.CYAN}{proc.name}{c.RESET} (pid {c.YELLOW}{proc.pid}{c.RESET})")
        # Prepare prefix for children
        extension = "  " if is_last else "│ "
        child_prefix = prefix + extension

    # Print children
    for i, child in enumerate(proc.children):
        is_last_child = (i == len(proc.children) - 1)
        print_tree(child, child_prefix, is_last_child, is_root=False)


def print_json_output(proc: ProcessInfo):
    """Print JSON output."""
    output = {
        "pid": proc.pid,
        "name": proc.name,
        "ppid": proc.ppid,
        "user": proc.user,
        "command": proc.cmd,
        "start_time": proc.start_time.isoformat(),
        "uptime_seconds": int((datetime.now() - proc.start_time).total_seconds()),
        "restart_count": proc.restart_count,
        "memory_kb": proc.rss_kb,
        "ancestry": [{"pid": p.pid, "name": p.name} for p in proc.ancestry],
        "source": proc.source,
        "source_detail": proc.source_detail,
        "working_directory": proc.cwd,
        "git_repo": proc.git_repo,
        "git_branch": proc.git_branch,
        "container_name": proc.container_name,
        "container_image": proc.container_image,
        "listening_addresses": proc.listening_addresses,
        "warnings": get_warnings(proc)
    }
    print(json.dumps(output, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description='wayr - Why Are You Running? Explains why processes exist.',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('name', nargs='?', help='Process or service name to look up')
    parser.add_argument('-p', '--pid', type=int, help='PID to look up')
    parser.add_argument('-o', '--port', type=int, help='Port to look up')
    parser.add_argument('--exact', action='store_true', help='Use exact name matching')
    parser.add_argument('-s', '--short', action='store_true', help='Show only ancestry')
    parser.add_argument('-t', '--tree', action='store_true', help='Show process tree')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--verbose', action='store_true', help='Show extended information')
    parser.add_argument('--env', action='store_true', help='Show environment variables')
    parser.add_argument('--warnings', action='store_true', help='Show only warnings')
    parser.add_argument('--no-color', action='store_true', help='Disable colored output')
    parser.add_argument('--debug-man', action='store_true', help='Debug man page parsing (shows raw NAME section)')
    parser.add_argument('-v', '--version', action='version', version=f'wayr {VERSION}')

    args = parser.parse_args()

    # Check OS support
    if not (IS_LINUX or IS_MACOS):
        print(f"{Colors.RED}Warning: wayr is optimized for Linux and macOS. Your OS ({platform.system()}) may not be fully supported.{Colors.RESET}", file=sys.stderr)

    # Disable colors if requested or not a TTY
    if args.no_color or not sys.stdout.isatty():
        Colors.disable()

    # Determine what to look up
    processes = []

    if args.pid:
        proc = get_process_info(args.pid)
        if proc:
            processes = [proc]
        else:
            print(f"{Colors.RED}Process with PID {args.pid} not found{Colors.RESET}", file=sys.stderr)
            print(f"\n{Colors.DIM}Troubleshooting tips:{Colors.RESET}", file=sys.stderr)
            print(f"  • Verify the PID exists: ps -p {args.pid}", file=sys.stderr)
            print(f"  • The process may have terminated", file=sys.stderr)
            print(f"  • Check permissions: sudo may be required", file=sys.stderr)
            sys.exit(1)

    elif args.port:
        processes = find_process_by_port(args.port)
        if not processes:
            print(f"{Colors.RED}No process listening on port {args.port}{Colors.RESET}", file=sys.stderr)
            print(f"\n{Colors.DIM}Troubleshooting tips:{Colors.RESET}", file=sys.stderr)
            print(f"  • Verify the port number is correct", file=sys.stderr)
            print(f"  • Check if any process is listening: lsof -i :{args.port}", file=sys.stderr)
            print(f"  • The process might be listening on a different interface", file=sys.stderr)
            sys.exit(1)

    elif args.name:
        processes = find_processes_by_name(args.name, args.exact)
        if not processes:
            match_type = "exact" if args.exact else "substring"
            print(f"{Colors.RED}No processes found matching '{args.name}' ({match_type} match){Colors.RESET}", file=sys.stderr)
            print(f"\n{Colors.DIM}Troubleshooting tips:{Colors.RESET}", file=sys.stderr)
            print(f"  • Try without --exact flag for fuzzy matching", file=sys.stderr)
            print(f"  • List all processes: ps aux", file=sys.stderr)
            print(f"  • Check if process name is abbreviated in ps output", file=sys.stderr)
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)

    # Handle multiple matches
    if len(processes) > 1 and not args.short and not args.tree:
        print(f"{Colors.YELLOW}Multiple matching processes found:{Colors.RESET}")
        for i, proc in enumerate(processes, 1):
            print(f"[{i}] {Colors.CYAN}{proc.name}{Colors.RESET} (pid {Colors.YELLOW}{proc.pid}{Colors.RESET})")
            print(f"    {Colors.DIM}{proc.cmd}{Colors.RESET}")
        print(f"\n{Colors.BOLD}Re-run with:{Colors.RESET}")
        print(f"  wayr --pid <pid>")
        sys.exit(0)

    # Process each match
    for i, proc in enumerate(processes):
        if i > 0:
            print()

        # Build context
        proc.ancestry = build_ancestry(proc)
        detect_source(proc)
        detect_git_context(proc)
        detect_listening_ports(proc)

        # Output
        if args.warnings:
            warnings = get_warnings(proc)
            if warnings:
                for warning in warnings:
                    print(f"{Colors.YELLOW}⚠{Colors.RESET}  {warning}")
        elif args.json:
            print_json_output(proc)
        elif args.short:
            print_short(proc)
        elif args.tree:
            build_process_tree(proc.ancestry[0] if proc.ancestry else proc)
            print_tree(proc.ancestry[0] if proc.ancestry else proc)
        else:
            print_process_info(proc, args)


if __name__ == '__main__':
    main()
