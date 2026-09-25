# `isempty(stream)`

Returns `true` if `stream` produces no values, else `false`.

## Example 1

**Command**: `jq 'isempty(empty)'`
**Input**: `null`
**Output**: `true`

## Example 2

**Command**: `jq 'isempty(range(1))'`
**Input**: `null`
**Output**: `false`
