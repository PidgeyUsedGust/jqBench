# `path(expr)`

Emits the path (as an array of keys/indices) to each value produced by `expr` from the current input. Useful with `getpath`, `setpath`, or for searching nested structures.

## Example 1

**Command**: `jq 'path(.. | .a?)'`
**Input**: `[{"a":1}, {"b":{"a":2}}]`
**Output**: `[0,"a"]` then `[1,"b","a"]`
