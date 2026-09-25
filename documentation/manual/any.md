# `any`

Forms: `any(stream)` or `any(stream; cond)`. Returns `true` if any value from `stream` is truthy (first form) or any value makes `cond` truthy (second form). Otherwise `false`. Short-circuits.

## Example 1

**Command**: `jq 'any([false, null, 1][])'`
**Input**: `null`
**Output**: `true`

## Example 2

**Command**: `jq 'any(range(5); .==3)'`
**Input**: `null`
**Output**: `true`
