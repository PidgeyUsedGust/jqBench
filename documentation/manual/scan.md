# `scan(regex; flags?)`

Emits a match object for each non-overlapping regex match.

## Example 1

**Command**: `jq 'scan("[a-z]+") | .string'`
**Input**: `"ab12cd"`
**Output**: `"ab"` then `"cd"`
