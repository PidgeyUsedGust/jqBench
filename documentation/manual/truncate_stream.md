# `truncate_stream(stream)`

Truncates path elements from a stream of `[path, value]` pairs (as from `tostream`). Useful for pruning deeper paths.

## Example 1

**Command**: `jq 'tostream | truncate_stream(.[0:-1])'`
**Input**: `{"a":[1]}`
**Output**: (truncated path/value pairs)
