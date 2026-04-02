# Contract: CLI --curves Flag

## Command: `xlight-analyze generate`

### New flag

```
--curves MODE    Value curve generation mode (default: all)
                 Choices: all, brightness, speed, color, none
```

### Behavior

| Mode | Brightness curves | Speed curves | Color curves | Chord accents |
|------|------------------|-------------|-------------|---------------|
| `all` | Yes | Yes | Yes | Yes (if thresholds met) |
| `brightness` | Yes | No | No | No |
| `speed` | No | Yes | No | No |
| `color` | No | No | Yes | Yes (if thresholds met) |
| `none` | No | No | No | No |

### Examples

```bash
# Default: all value curves enabled
xlight-analyze generate song.mp3 layout.xml

# Brightness curves only
xlight-analyze generate song.mp3 layout.xml --curves brightness

# No curves (static parameters)
xlight-analyze generate song.mp3 layout.xml --curves none

# Override config file setting via CLI
xlight-analyze generate song.mp3 layout.xml --curves all
```

### Config file equivalent

In TOML generation profile (`~/.xlight/generation.toml` or per-song config):

```toml
[generation]
curves_mode = "all"    # all | brightness | speed | color | none
```

CLI `--curves` takes precedence over config file when both are specified.
