# `strptime(fmt)`

Parses a date/time string using the given format into a broken-down time array.

## Example 1

**Command**: `jq 'strptime("%Y-%m-%d")'`
**Input**: `"1970-01-01"`
**Output**: `[1970,1,1,0,0,0]`
