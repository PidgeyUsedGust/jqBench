# `first(stream?)`

Returns the first value produced by its input or by the `stream` expression, if any. If there is no value, produces `null` (no output in some older versions). Equivalent to `.[0]` for arrays but works on any generator.

## Example 1

**Command**: `jq 'first(range(10))'`
**Input**: `null`
**Output**: `0`

## Example 2

**Command**: `jq 'first(empty)'`
**Input**: `null`
**Output**: `null`
