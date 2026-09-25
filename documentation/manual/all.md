# `all`

Forms: `all(stream)` or `all(stream; cond)`. Returns `true` if every value in `stream` is truthy / satisfies `cond`, and at least one value was seen; returns `false` otherwise. Empty stream yields `false`.

## Example 1

**Command**: `jq 'all([1,2,3][])'`
**Input**: `null`
**Output**: `true`

## Example 2

**Command**: `jq 'all(range(5); . < 5)'`
**Input**: `null`
**Output**: `true`
