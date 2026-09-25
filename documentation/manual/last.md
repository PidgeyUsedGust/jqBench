# `last(stream?)`

Returns the last value produced by its input or by `stream`. If the stream is empty, returns `null`.

## Example 1

**Command**: `jq 'last(range(5))'`
**Input**: `null`
**Output**: `4`

## Example 2

**Command**: `jq 'last(empty)'`
**Input**: `null`
**Output**: `null`
