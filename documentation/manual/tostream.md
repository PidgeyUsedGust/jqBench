# `tostream`

Emits a stream of `[path, value]` arrays representing every leaf and intermediate node in the input JSON structure. Each `path` is an array of keys/indices leading to `value`.

## Example 1

**Command**: `jq 'tostream'`
**Input**: `{"a":[1]}`
**Output**: (stream of path/value pairs)

## Example 2

**Command**: `jq 'tostream | fromstream'`
**Input**: `{"x":{"y":2}}`
**Output**: `{"x":{"y":2}}`
