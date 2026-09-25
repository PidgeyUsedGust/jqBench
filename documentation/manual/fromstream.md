# `fromstream(stream)`

Reconstructs a JSON value from a stream of `[path,value]` arrays produced by `tostream`.

## Example 1

**Command**: `jq 'tostream | fromstream'`
**Input**: `{"a":[1]}`
**Output**: `{"a":[1]}`
