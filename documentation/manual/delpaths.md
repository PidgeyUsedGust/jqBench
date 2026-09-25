# `delpaths(paths_array)`

Deletes all paths listed (each path is an array of keys/indices). Use with `paths` or custom lists.

## Example 1

**Command**: `jq 'delpaths([["a"],["b","c"]])'`
**Input**: `{"a":1,"b":{"c":2,"d":3}}`
**Output**: `{"b":{"d":3}}`
