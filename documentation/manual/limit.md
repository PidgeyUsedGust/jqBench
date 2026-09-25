# `limit(n; stream)`

Passes through at most `n` results from `stream` and then stops. Helpful to short-circuit expensive generators.

## Example 1

**Command**: `jq '[limit(3; range(10))]'`
**Input**: `null`
**Output**: `[0,1,2]`
