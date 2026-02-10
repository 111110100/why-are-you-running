# Man Page Integration - "What it is" Feature

## Overview

Starting in version 1.0.5, `wayr` automatically extracts and displays command descriptions from man pages, helping you understand what each process does without needing to look it up manually.

## What It Does

When you query a process, wayr:
1. Extracts the command name from the process
2. Looks up its man page
3. Parses the NAME section
4. Displays the description in a new "What it is" field

## Example Output

### Before (v1.0.4)
```
Target      : cat
Process     : cat (pid 12345)
User        : john
Command     : cat /var/log/syslog
Started     : 5 minutes ago
```

### After (v1.0.5)
```
Target      : cat
Process     : cat (pid 12345)
User        : john
Command     : cat /var/log/syslog
What it is  : Concatenate and print files
Started     : 5 minutes ago
```

## Supported Commands

### System Utilities
```bash
$ wayr cat
What it is  : Concatenate and print files

$ wayr ls
What it is  : List directory contents

$ wayr grep
What it is  : Print lines that match patterns

$ wayr find
What it is  : Search for files in a directory hierarchy
```

### Networking Tools
```bash
$ wayr ssh
What it is  : OpenSSH remote login client

$ wayr curl
What it is  : Transfer data from or to a server

$ wayr nginx
What it is  : HTTP and reverse proxy server
```

### Development Tools
```bash
$ wayr git
What it is  : The stupid content tracker

$ wayr make
What it is  : GNU make utility to maintain groups of programs

$ wayr docker
What it is  : Docker container runtime
```

## How It Works

### Man Page Parsing

The feature parses the NAME section of man pages, which typically follows this format:

**Standard Format:**
```
NAME
     command - description here
```

**BSD Format:**
```
NAME
     command – description here
```

**Multiple Commands:**
```
NAME
     cat, zcat, bzcat - concatenate and print files
```

### Dash Variants

The parser handles different dash styles:
- `-` (hyphen)
- `–` (en-dash)
- `—` (em-dash)

### Extraction Logic

```python
# Example man page NAME section:
NAME
     cat – concatenate and print files

# Extracted:
"Concatenate and print files"
```

The description:
1. Has the first letter capitalized
2. Has trailing periods removed
3. Is trimmed of whitespace

## Smart Interpreter Detection

For interpreted languages, wayr tries to be smart about what to show:

### Python Scripts
```bash
# Command: python3 /usr/local/bin/myapp.py
# Instead of showing Python's description, tries to find man page for "myapp"

$ wayr --pid 12345
Command     : python3 /usr/local/bin/myapp.py
What it is  : My custom application (if man page exists for myapp)
```

### Node.js Applications
```bash
# Command: node /opt/server.js
# Tries "server" man page first, falls back to "node" if not found

$ wayr node
Command     : node /opt/server.js
What it is  : Server-side JavaScript runtime
```

### Supported Interpreters
- `python`, `python2`, `python3`
- `node`, `nodejs`
- `ruby`
- `perl`
- `php`
- `bash`, `sh`, `zsh`, `fish`
- `java`

## When Description Is Not Shown

The "What it is" field is omitted when:

1. **No man page available**
   ```bash
   $ wayr myapp
   # Custom app with no man page - field not shown
   ```

2. **Man page has no NAME section**
   ```bash
   $ wayr obscure-tool
   # Malformed man page - field not shown
   ```

3. **Command is a complex shell expression**
   ```bash
   $ wayr --pid 9999
   Command     : bash -c "while true; do echo hi; done"
   # No simple command to look up - field not shown
   ```

## Man Page Format Examples

### Linux (GNU Style)
```
NAME
       cat - concatenate files and print on the standard output

SYNOPSIS
       cat [OPTION]... [FILE]...
```

### macOS (BSD Style)
```
NAME
     cat – concatenate and print files

SYNOPSIS
     cat [-benstuv] [file ...]
```

### Multiple Commands (Aliases)
```
NAME
       grep, egrep, fgrep, rgrep - print lines that match patterns
```
Result: "Print lines that match patterns"

## Implementation Details

### Function: get_command_description()

```python
def get_command_description(cmd: str) -> Optional[str]:
    """Get the description of a command from its man page NAME section."""
    
    # Extract base command name
    base_cmd = os.path.basename(cmd.split()[0])
    
    # Handle interpreters
    if base_cmd in ['python', 'node', ...]:
        # Try to get script name instead
        base_cmd = extract_script_name(cmd)
    
    # Get man page
    rc, stdout, _ = run_command(['man', base_cmd])
    
    # Parse NAME section
    description = parse_name_section(stdout)
    
    # Extract text after dash
    return extract_after_dash(description)
```

### Performance

- **Cached**: Man pages are system-level and static, so results could be cached
- **Fast**: Man page lookup is usually < 0.01 seconds
- **Non-blocking**: If man lookup fails, wayr continues normally

### Error Handling

All exceptions are caught silently:
- Missing man page → No "What it is" field
- Malformed man page → No "What it is" field  
- Permission errors → No "What it is" field

The feature never causes wayr to fail, it just silently omits the field.

## Customization

### Disable Man Page Lookups

Currently not configurable, but you can comment out the line in `print_process_info()`:

```python
# Get command description from man page
# cmd_desc = get_command_description(proc.cmd)
# if cmd_desc:
#     print(f"{c.BOLD}What it is{c.RESET}  : {cmd_desc}")
```

### Add Custom Descriptions

You could extend the function to check a custom database first:

```python
CUSTOM_DESCRIPTIONS = {
    'myapp': 'My custom application',
    'internal-tool': 'Internal development tool',
}

def get_command_description(cmd: str) -> Optional[str]:
    base_cmd = extract_base_command(cmd)
    
    # Check custom descriptions first
    if base_cmd in CUSTOM_DESCRIPTIONS:
        return CUSTOM_DESCRIPTIONS[base_cmd]
    
    # Fall back to man page
    return parse_man_page(base_cmd)
```

## Examples in Different Scenarios

### Web Server Investigation
```bash
$ wayr nginx

Target      : nginx
Process     : nginx (pid 1234)
User        : www-data
Command     : nginx -g daemon off;
What it is  : HTTP and reverse proxy server
Started     : 14 days ago
Why It Exists :
  systemd (pid 1) → nginx (pid 1234)
Source      : systemd (nginx.service)
Listening   : 0.0.0.0:80, 0.0.0.0:443
```

### Database Server
```bash
$ wayr postgres

Target      : postgres
Process     : postgres (pid 5678)
User        : postgres
Command     : /usr/lib/postgresql/14/bin/postgres
What it is  : PostgreSQL database server
Started     : 30 days ago
Why It Exists :
  systemd (pid 1) → postgres (pid 5678)
Source      : systemd (postgresql.service)
```

### Development Tool
```bash
$ wayr --port 3000

Target      : node
Process     : node (pid 9876)
User        : developer
Command     : node server.js
What it is  : Server-side JavaScript runtime
Started     : 2 hours ago
Why It Exists :
  systemd (pid 1) → bash (pid 8901) → node (pid 9876)
Source      : interactive shell (bash)
Working Dir : /home/developer/my-app
Git Repo    : my-app (feature/new-api)
Listening   : 127.0.0.1:3000
```

## Benefits

### For Beginners
- Instantly understand unfamiliar commands
- No need to `man <command>` separately
- Learn what tools do while debugging

### For Experts
- Quick refresher on tool purpose
- Helpful when dealing with unfamiliar systems
- Good for documentation and screenshots

### For Teams
- Self-documenting output
- Better communication in incident reports
- Helps onboarding new team members

## Limitations

1. **System-dependent**: Description depends on installed man pages
2. **Language-specific**: Only works for commands with man pages
3. **Static**: Doesn't help with custom scripts without man pages
4. **Format variations**: Some man pages don't follow standard format

## Future Enhancements

Potential improvements:

- **Cache man page lookups** for better performance
- **Support for info pages** (GNU documentation)
- **Custom description database** for tools without man pages
- **Description from --help** output as fallback
- **Multi-language support** for non-English man pages

## Related Commands

To view full man page:
```bash
man <command>
```

To search man pages:
```bash
apropos <keyword>
```

To see which man page would be used:
```bash
which <command>
man -w <command>
```

## Conclusion

The "What it is" feature makes wayr output more self-explanatory by automatically showing what each command does. It's a small addition that significantly improves the user experience, especially when debugging unfamiliar systems or sharing output with teammates.
