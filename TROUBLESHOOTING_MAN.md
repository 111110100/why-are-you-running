# Troubleshooting Man Page Display

## Problem: "What it is" field not showing for a command with a man page

If you have a man page for a command (e.g., `talagentd`) but wayr isn't displaying the description, use the debug mode to diagnose the issue.

## Step 1: Verify Man Page Exists

First, confirm the man page exists:

```bash
man talagentd
```

If this shows the man page, proceed to step 2.

## Step 2: Use Debug Mode

Run wayr with the `--debug-man` flag:

```bash
wayr --pid <pid> --debug-man
```

Or for a specific command:

```bash
wayr talagentd --debug-man
```

### Example Debug Output

```bash
$ wayr talagentd --debug-man

Target      : talagentd
Process     : talagentd (pid 12345)
User        : root
Command     : /usr/bin/talagentd --daemon

[DEBUG] Trying to get man page for: talagentd
[DEBUG] Got man page output (1523 chars)
[DEBUG] Found NAME section at line 45
[DEBUG] Exiting NAME section at line 48 (found: SYNOPSIS)
[DEBUG] Raw NAME content: 'talagentd - Talos Vantage monitoring agent'
[DEBUG] Cleaned description: 'talagentd - Talos Vantage monitoring agent'
[DEBUG] Found dash '-', extracted: 'Talos Vantage monitoring agent'
[DEBUG] Returning: 'Talos Vantage monitoring agent'
What it is  : Talos Vantage monitoring agent

Started     : ...
```

## Common Issues and Solutions

### Issue 1: "No description lines found in NAME section"

**Debug output:**
```
[DEBUG] Got man page output (500 chars)
[DEBUG] No description lines found in NAME section
```

**Cause:** The man page doesn't have a NAME section, or it's formatted unusually.

**Solution:** Check the actual man page format:
```bash
man talagentd | head -30
```

Look for the NAME section. It should look like:
```
NAME
       talagentd - description here
```

If the NAME section is missing or has unusual formatting, wayr can't extract it.

### Issue 2: "Found NAME section" but no description extracted

**Debug output:**
```
[DEBUG] Found NAME section at line 10
[DEBUG] Exiting NAME section at line 11 (found: SYNOPSIS)
[DEBUG] Raw NAME content: ''
[DEBUG] No description lines found in NAME section
```

**Cause:** The NAME section is empty or contains only the section header.

**Solution:** The man page is malformed. Check:
```bash
man talagentd 2>&1 | grep -A 5 "^NAME"
```

### Issue 3: "Could not extract usable description"

**Debug output:**
```
[DEBUG] Raw NAME content: 'talagentd(8) Talos monitoring daemon'
[DEBUG] Cleaned description: 'talagentd(8) Talos monitoring daemon'
[DEBUG] No dash found, trying alternative parsing
[DEBUG] Could not extract usable description
```

**Cause:** The NAME section doesn't follow standard format (no dash separator).

**Solution:** The man page uses a non-standard format. This is a limitation of the current parser.

**Workaround:** The parser tries to handle this by looking for the command name followed by text, but if the format is too unusual, it may fail.

### Issue 4: Description too short

**Debug output:**
```
[DEBUG] Found dash '-', extracted: 'Mon'
[DEBUG] Description too short (3 chars), skipping
```

**Cause:** The parser incorrectly split on a dash that wasn't the separator.

**Solution:** This is a parsing edge case. The man page may have an unusual format.

## Man Page Format Examples

### BSD mdoc Format (macOS/BSD) - **NOW SUPPORTED!**
```
.Sh NAME
.Nm talagentd
.Nd helper agent for application lifecycle features
```

**Result:** "Helper agent for application lifecycle features"

This format uses the `.Nd` macro to define the description. Version 1.0.7+ now supports this format natively.

### Standard Format (Linux/GNU) - Works
```
NAME
       talagentd - Talos Vantage monitoring agent

SYNOPSIS
       talagentd [options]
```

### BSD Format (Works)
```
NAME
     talagentd – Talos Vantage monitoring agent

SYNOPSIS
     talagentd [-d] [-c config]
```

### Multiple Commands (Works)
```
NAME
       talagentd, talctl - Talos monitoring tools

SYNOPSIS
       talagentd [options]
```

### Non-Standard Format (May Not Work)
```
NAME
       talagentd(8) Talos monitoring daemon
       
SYNOPSIS
       talagentd [options]
```

This format has no dash separator, so the parser tries alternative methods.

### Missing NAME Section (Won't Work)
```
SYNOPSIS
       talagentd [options]

DESCRIPTION
       talagentd is a monitoring agent...
```

This man page skips the NAME section entirely.

## Manual Fix

If wayr can't parse the man page, you can:

1. **File a bug report** with the man page format included
2. **Edit the wayr.py** to add a custom description for specific commands
3. **Fix the man page** if you maintain it

### Adding Custom Descriptions

Edit `wayr.py` and add to the `get_command_description` function:

```python
def get_command_description(cmd: str, debug: bool = False) -> Optional[str]:
    base_cmd = os.path.basename(cmd.split()[0])
    
    # Custom descriptions for commands with non-standard man pages
    CUSTOM_DESCRIPTIONS = {
        'talagentd': 'Talos Vantage monitoring agent',
        'myapp': 'My custom application',
    }
    
    if base_cmd in CUSTOM_DESCRIPTIONS:
        return CUSTOM_DESCRIPTIONS[base_cmd]
    
    # ... rest of function
```

## Reporting Issues

When reporting a man page parsing issue, include:

1. **Command name**
2. **Debug output** from `--debug-man`
3. **Man page NAME section:**
   ```bash
   man talagentd | head -20
   ```

Example bug report:

```
Command: talagentd
Debug output shows:
  [DEBUG] Found NAME section at line 10
  [DEBUG] Raw NAME content: 'talagentd(8) Talos agent'
  [DEBUG] Could not extract usable description

Man page NAME section:
NAME
       talagentd(8) Talos agent
       
SYNOPSIS
       talagentd [options]
```

This helps improve the parser to handle more formats!

## Summary

1. Use `--debug-man` to see what's happening
2. Check the actual man page format with `man <command>`
3. Report unusual formats so we can improve the parser
4. As a workaround, add custom descriptions for problematic commands

The debug output will show you exactly where the parsing is failing and help diagnose the issue.
