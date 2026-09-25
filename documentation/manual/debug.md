# `debug`

Writes the input (with prefix) to stderr, then passes it through unchanged.

## Example 1

**Command**: `jq '42 | debug | .+1'`
**Input**: `null`
**Output**: `43`
