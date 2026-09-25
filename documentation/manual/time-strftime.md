# `strftime(fmt)`

Formats a broken-down time array according to POSIX `strftime` format string.

## Example 1

**Command**: `jq 'strftime("%Y-%m-%d")'`
**Input**: `[1970,1,1,0,0,0]`
**Output**: `"1970-01-01"`
