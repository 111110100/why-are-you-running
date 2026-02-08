# macOS Testing Guide

This guide helps you test `wayr` on macOS to verify all features work correctly.

## Prerequisites

Make sure you have these tools (most are pre-installed on macOS):
```bash
# Check which tools are available
which ps      # Should be: /bin/ps
which lsof    # Should be: /usr/sbin/lsof
which python3 # Should be: /usr/bin/python3 or similar
```

## Basic Tests

### Test 1: Find Your Current Shell
```bash
# Get your shell's PID
echo $$

# Query it with wayr
./wayr.py --pid <your-shell-pid>
```

**Expected Output:**
- Process name: bash, zsh, or fish (depending on your shell)
- User: your username
- Command: full path to your shell
- Ancestry chain showing Terminal.app or iTerm2

### Test 2: Find a Common Process
```bash
# Find all Python processes
./wayr.py python

# Or a specific one
./wayr.py --pid 1
```

**Expected Output:**
- List of matching processes, or
- Details about PID 1 (launchd on macOS)

### Test 3: Port Detection
```bash
# Start a simple Python server in another terminal
python3 -m http.server 8000

# Then find what's on port 8000
./wayr.py --port 8000
```

**Expected Output:**
- Process: python3
- Listening: 0.0.0.0:8000 or *:8000
- Warning about public interface

### Test 4: JSON Output
```bash
./wayr.py --pid $$ --json | python3 -m json.tool
```

**Expected Output:**
- Valid JSON with all process details

### Test 5: Process Tree
```bash
# Find launchd (init process on macOS)
./wayr.py --pid 1 --tree
```

**Expected Output:**
- launchd at the root
- Tree of child processes

## macOS-Specific Features

### launchd Detection
```bash
# Find any process managed by launchd
./wayr.py Dock
```

**Expected:**
- Source: launchd
- Ancestry includes launchd (pid 1)

### Working Directory
```bash
# Create a process in a specific directory
cd ~/Desktop
sleep 1000 &
SLEEP_PID=$!

# Query it
./wayr.py --pid $SLEEP_PID

# Cleanup
kill $SLEEP_PID
```

**Expected:**
- Working Dir: /Users/<you>/Desktop

### Git Repository Context
```bash
# In a git repository
cd /path/to/your/git/repo
sleep 1000 &
SLEEP_PID=$!

./wayr.py --pid $SLEEP_PID

kill $SLEEP_PID
```

**Expected:**
- Git Repo: <repo-name>
- Git Branch: <current-branch>

## Common macOS Processes to Test

### Finder
```bash
./wayr.py Finder
```

### Safari
```bash
./wayr.py Safari
```

### Terminal/iTerm
```bash
./wayr.py Terminal
# or
./wayr.py iTerm
```

### System Processes
```bash
# WindowServer
sudo ./wayr.py WindowServer

# SystemUIServer
./wayr.py SystemUIServer

# configd (network configuration)
sudo ./wayr.py configd
```

## Permission Issues

If you get "Permission denied" or can't access some process info:

```bash
# Some processes require sudo
sudo ./wayr.py --pid <pid>
```

## Troubleshooting

### Issue: "Process with PID X not found" but `ps -p X` shows it
```bash
# Try with sudo
sudo ./wayr.py --pid X

# Check if process exists
ps -p X -o pid,ppid,user,comm,command
```

### Issue: Port detection doesn't work
```bash
# Verify lsof is available
which lsof

# Test lsof directly
lsof -i :<port> -sTCP:LISTEN

# If lsof is missing, install it via Homebrew
brew install lsof
```

### Issue: Working directory shows as "None"
This is normal for:
- System processes
- Processes you don't own (without sudo)
- Processes that have changed their root directory

## Comparison with Linux

| Feature | Linux | macOS | Notes |
|---------|-------|-------|-------|
| Process info | `/proc` | `ps` | Both work |
| Port detection | `ss` or `/proc/net/tcp` | `lsof` | macOS uses lsof |
| Working dir | `/proc/[pid]/cwd` | `lsof -d cwd` | Different methods |
| systemd | ✅ | ❌ | macOS uses launchd |
| launchd | ❌ | ✅ | macOS init system |
| Docker | ✅ | ✅ | Works on both |

## Expected Differences

These are **normal** on macOS:

1. **No systemd detection** - macOS uses launchd instead
2. **Different ancestry** - Processes may have Terminal.app or launchd as parents
3. **No `/proc` warnings** - macOS doesn't use `/proc`, uses `ps` instead
4. **Memory in MB not KB** - macOS `ps` reports differently

## Full Example Session

```bash
# 1. Check version
./wayr.py --version
# Output: wayr 1.0.2

# 2. Find your current shell
./wayr.py --pid $$
# Output: Shows your shell with ancestry

# 3. Start a web server
python3 -m http.server 8080 &
SERVER_PID=$!

# 4. Find it by port
./wayr.py --port 8080
# Output: Shows python3 listening on port 8080

# 5. Find it by name
./wayr.py python3
# Output: Lists all python3 processes

# 6. Get JSON
./wayr.py --pid $SERVER_PID --json
# Output: JSON with all details

# 7. See ancestry
./wayr.py --pid $SERVER_PID --short
# Output: launchd (pid 1) → ... → python3 (pid X)

# 8. Cleanup
kill $SERVER_PID
```

## Reporting Issues

If something doesn't work on macOS, please report:

1. macOS version: `sw_vers`
2. Python version: `python3 --version`
3. The exact command you ran
4. The actual output
5. Output of: `ps -p <pid> -o pid,ppid,user,comm,command`

Example bug report:
```
OS: macOS 14.1 (Sonoma)
Python: 3.11.5
Command: ./wayr.py --pid 12345
Error: Process with PID 12345 not found

ps output:
  PID  PPID USER    COMM      COMMAND
12345  1234 user    python3   /usr/bin/python3 script.py
```
