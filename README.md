# wayr - Why Are You Running?

> *Named after the popular meme: "Why are you running?!"*
>
> ![Why are you running?](./wayr.webp)
>
> **Version 1.0.9** - Complete man page format support (BSD mdoc, troff, standard)

A diagnostic utility that answers the question: **Why is this process/service/port running?**

When something is running on a system—whether it's a process, service, or something bound to a port—there's always a cause. That cause is often indirect, non-obvious, or spread across multiple layers like supervisors, containers, services, or shells.

Existing tools (`ps`, `top`, `lsof`, `ss`, `systemctl`, `docker ps`) show *what* is running. **wayr** shows *why*.

## Features

- 🔍 **Causal Chain Analysis** - Traces how a process came to exist, from init to your process
- 🎯 **Multiple Entry Points** - Query by process name, PID, or port
- 🐳 **Multi-Source Detection** - Automatically detects systemd, Docker, PM2, cron, and more
- 📊 **Context Awareness** - Shows git repos, containers, working directories, and listening ports
- 📖 **Man Page Integration** - Displays command descriptions from man pages ("What it is")
- ⚠️ **Smart Warnings** - Alerts on root processes, public binds, high memory, and more
- 🎨 **Multiple Output Modes** - Full report, short ancestry, tree view, or JSON
- 🔒 **Read-Only & Safe** - No destructive operations, just analysis
- ⚡ **Blazing Fast** - Optimized algorithms, single ps call for tree building

## Installation

### Quick Install

```bash
# Download and make executable
curl -o wayr https://raw.githubusercontent.com/111110100/wayr/main/wayr.py
chmod +x wayr
sudo mv wayr /usr/local/bin/
```

### From Source

```bash
git clone https://github.com/111110100/wayr.git
cd wayr
chmod +x wayr.py
sudo ln -s "$(pwd)/wayr.py" /usr/local/bin/wayr
```

### Requirements

- Python 3.6+
- **Linux** or **macOS** (Darwin)
- **No external dependencies required!**

Optional tools for enhanced features:
- `lsof` - for port detection (usually pre-installed on macOS/Linux)
- `systemctl` - for systemd service detection (Linux)
- `docker` - for container information
- `pm2` - for PM2 process manager details

**Platform Support:**
- ✅ **Linux**: Full support with `/proc` filesystem parsing
- ✅ **macOS**: Full support using `ps`, `lsof`, and macOS-specific tools
- ⚠️ **Other Unix**: Basic support via `ps` command (untested)

## Usage

### Basic Queries

**By process name:**
```bash
wayr node
wayr nginx
wayr postgres
```

**By PID:**
```bash
wayr --pid 1234
wayr -p 1234
```

**By port:**
```bash
wayr --port 8080
wayr -o 3000
```

### Output Modes

**Default - Full Report:**
```bash
wayr node
```

Output:
```
Target      : node
Process     : node (pid 14233)
User        : pm2
Command     : node index.js
What it is  : Server-side JavaScript runtime
Started     : 2 days ago (Mon 2025-02-02 11:42:10 +05:30)
Restarts    : 1
Why It Exists :
  systemd (pid 1) → pm2 (pid 5034) → node (pid 14233)
Source      : pm2
Working Dir : /opt/apps/expense-manager
Git Repo    : expense-manager (main)
Listening   : 127.0.0.1:5001
```

**Short - Ancestry Only:**
```bash
wayr --port 5000 --short
```

Output:
```
systemd (pid 1) → PM2 v5.3.1: God (pid 1481580) → python (pid 1482060)
```

**Tree - Process Hierarchy:**
```bash
./wayr.py --pid 143895 --tree
```

Output:
```
systemd (pid 1)
├─init-systemd(Ub (pid 2)
│ └─SessionLeader (pid 143858)
│   └─Relay(143860) (pid 143859)
│     └─bash (pid 143860)
│       └─sh (pid 143886)
│         └─node (pid 143895)
│           ├─node (pid 143930)
│           ├─node (pid 144189)
│           └─node (pid 144234)
└─dockerd (pid 1200)
  └─containerd-shim (pid 5400)
```

**JSON - Machine Readable:**
```bash
wayr nginx --json
```

Output:
```json
{
  "pid": 2311,
  "name": "nginx",
  "ppid": 1,
  "user": "www-data",
  "command": "nginx -g daemon off;",
  "start_time": "2025-02-05T10:30:22",
  "ancestry": [
    {"pid": 1, "name": "systemd"}
  ],
  "source": "systemd",
  "source_detail": "nginx.service",
  "listening_addresses": ["0.0.0.0:80", "0.0.0.0:443"],
  "warnings": ["Listening on public interface (0.0.0.0:80)"]
}
```

### Advanced Options

**Exact Name Matching:**
```bash
# Fuzzy match (default) - finds "nginx", "nginx-debug", etc.
wayr nginx

# Exact match only
wayr nginx --exact
```

**Show Environment Variables:**
```bash
wayr node --env
```

**Verbose Output:**
```bash
wayr postgres --verbose
```

**Warnings Only:**
```bash
wayr --pid 1234 --warnings
```

**Disable Colors:**
```bash
wayr nginx --no-color
```

## Use Cases

### Debugging Port Conflicts

```bash
$ wayr --port 8080

Target      : node
Process     : node (pid 12345)
User        : john
Command     : node server.js
Started     : 5 minutes ago
Why It Exists :
  systemd (pid 1) → bash (pid 8901) → node (pid 12345)
Source      : interactive shell (bash)
Listening   : 0.0.0.0:8080

Warnings:
  ⚠  Listening on public interface (0.0.0.0:8080)
```

**What you learn:**
- Process started from an interactive shell (not a service!)
- Running on public interface (security concern)
- Started recently (probably a dev server someone forgot)

### Understanding Service Restarts

```bash
$ wayr api-server

Target      : api-server
Process     : node (pid 54321)
User        : api
Command     : node dist/main.js
Started     : 10 seconds ago
Restarts    : 47
Why It Exists :
  systemd (pid 1) → api-server (pid 54321)
Source      : systemd (api-server.service)
Working Dir : /opt/api-server
Git Repo    : api-server (production)

Warnings:
  ⚠  Process has restarted 47 times
```

**What you learn:**
- Service is crash-looping (47 restarts!)
- Managed by systemd
- Running from production git branch
- Can now check: `journalctl -u api-server.service`

### Container Investigation

```bash
$ wayr --port 3000

Target      : node
Process     : node (pid 9876)
User        : root
Command     : docker-entrypoint.sh node app.js
Started     : 3 days ago
Why It Exists :
  systemd (pid 1) → dockerd (pid 1200) → containerd-shim (pid 5400) → node (pid 9876)
Source      : docker
Container   : web-app-prod
Image       : myorg/web-app:v2.1.0
Listening   : 0.0.0.0:3000

Warnings:
  ⚠  Process is running as root
  ⚠  Listening on public interface (0.0.0.0:3000)
```

**What you learn:**
- Running in Docker container "web-app-prod"
- Using specific image version (v2.1.0)
- Security issues: root user + public bind
- Can now inspect: `docker logs web-app-prod`

### Finding Orphaned Processes

```bash
$ wayr java --short

systemd (pid 1) → java (pid 23456)
```

**What you learn:**
- Java process has been orphaned (adopted by init/systemd)
- Parent process crashed or was killed
- May need manual cleanup

## Detected Sources

wayr automatically detects these process supervisors and contexts:

| Source | Detection Method |
|--------|-----------------|
| **systemd** | Ancestry analysis + `systemctl status` |
| **Docker** | Container runtime in ancestry + `docker ps` |
| **PM2** | PM2 daemon in ancestry + `pm2 jlist` |
| **Supervisor** | supervisord in ancestry |
| **cron** | cron daemon in ancestry |
| **Interactive Shell** | bash/zsh/fish with TTY |
| **Kubernetes** | Container labels (via Docker/containerd) |
| **launchd** | macOS service manager (when available) |

## Warning Types

wayr provides contextual warnings for common issues:

| Warning | Trigger |
|---------|---------|
| Running as root | Non-init process with UID 0 |
| Public interface bind | Listening on `0.0.0.0` or `::` |
| High restart count | More than 5 restarts |
| High memory usage | RSS > 1GB |
| Long running process | Uptime > 90 days |

## Command Reference

```
wayr [NAME] [OPTIONS]

Arguments:
  NAME                Process or service name

Options:
  -p, --pid PID       Look up by process ID
  -o, --port PORT     Look up by listening port
  --exact             Use exact name matching (no fuzzy search)
  -s, --short         Show only ancestry chain
  -t, --tree          Show process tree with children
  --json              Output as JSON
  --verbose           Show extended process information
  --env               Show environment variables
  --warnings          Show only warnings
  --no-color          Disable colored output
  --debug-man         Debug man page parsing (shows raw NAME section)
  -v, --version       Show version
  -h, --help          Show help message
```

## Examples Gallery

### Web Server Investigation
```bash
$ wayr nginx

Target      : nginx
Process     : nginx (pid 1234)
User        : www-data
Command     : nginx -g daemon off;
Started     : 14 days ago
Why It Exists :
  systemd (pid 1) → nginx (pid 1234)
Source      : systemd (nginx.service)
Working Dir : /
Listening   : 0.0.0.0:80, 0.0.0.0:443

Warnings:
  ⚠  Process has been running for 14 days
```

### Database Server
```bash
$ wayr postgres --short

systemd (pid 1) → postgres (pid 5678)
```

### Development Server
```bash
$ wayr --port 3000

Target      : vite
Process     : node (pid 98765)
User        : developer
Command     : vite dev
Started     : 2 hours ago
Why It Exists :
  systemd (pid 1) → bash (pid 45678) → npm (pid 98760) → node (pid 98765)
Source      : interactive shell (bash)
Working Dir : /home/developer/my-app
Git Repo    : my-app (feature/new-ui)
Listening   : 127.0.0.1:3000
```

### Microservice in Production
```bash
$ wayr api --json | jq .

{
  "pid": 12345,
  "name": "node",
  "command": "node dist/index.js",
  "source": "pm2",
  "source_detail": "api-gateway",
  "git_repo": "api-gateway",
  "git_branch": "main",
  "restart_count": 0,
  "uptime_seconds": 2592000,
  "listening_addresses": ["127.0.0.1:4000"]
}
```

## Limitations

- **Linux and macOS only** - Requires either `/proc` filesystem (Linux) or `ps`/`lsof` (macOS)
- **No historical data** - Shows current state only
- **Best-effort detection** - Some sources may not be detected
- **Read-only** - Cannot modify or kill processes
- **Local only** - Does not support remote systems

## Comparison with Other Tools

| Tool | What it shows | What wayr adds |
|------|---------------|----------------|
| `ps aux` | Process list | **Why** each process exists |
| `systemctl status` | Service status | Works for **all** processes, not just systemd |
| `docker ps` | Containers | Links containers to **host PIDs** |
| `lsof -i` | Ports in use | **Full causal chain** for port listeners |
| `pstree` | Process hierarchy | **Source detection** and **context** |
| `top` | Resource usage | **Why** high-resource processes exist |

## Contributing

Contributions welcome! Areas for improvement:

- macOS support (launchd integration)
- Kubernetes pod detection
- More process managers (runit, s6, etc.)
- Historical restart tracking
- Performance optimizations

## License

MIT License - see LICENSE file for details

## FAQ

**Q: Why "wayr"?**
A: Named after the "Why are you running?!" meme. Also short for "Why Are You Running".

**Q: Does it work on macOS?**
A: Yes! Version 1.0.2+ has full macOS support using `ps`, `lsof`, and native macOS tools.

**Q: Does it work on Linux?**
A: Yes! Linux has full support with both modern tools (`ss`, `systemctl`) and `/proc` filesystem fallbacks.

**Q: Can it kill processes?**
A: No. wayr is strictly read-only and diagnostic. Use `kill`, `systemctl stop`, `docker stop`, etc.

**Q: Why not just use ps/top/systemctl?**
A: Those tools show *state*. wayr shows *causality*. It connects the dots between multiple layers.

**Q: Does it require root?**
A: No, but some features require elevated privileges (reading other users' info, etc.).

**Q: What about Windows?**
A: Not currently supported. wayr requires Unix-like process management (Linux/macOS/BSD).

## Author

Created as a utility to reduce debugging time during incidents and outages.

## See Also

- `ps(1)` - Process status
- `systemctl(1)` - Control the systemd system
- `docker(1)` - Container management
- `lsof(8)` - List open files
- `pstree(1)` - Display process tree
