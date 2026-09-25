# `match(regex; flags?)`

Returns a match object for the first regex match in the input string.

## Example 1

**Command**: `jq 'match("[a-z]+") | .string'`
**Input**: `"abc123"`
**Output**: `"abc"`
