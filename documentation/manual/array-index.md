# `.[<number>]`

Array index. Returns the element at the zero-based index. Negative indices count from the end (`-1` last element). Out-of-range indices yield `null`.

## Example 1

**Command**: `jq '.[0]'`
**Input**: `[1,2,3]`
**Output**: `1`

## Example 2

**Command**: `jq '.[-1]'`
**Input**: `[1,2,3]`
**Output**: `3`

## Example 3

**Command**: `jq '.[10]'`
**Input**: `[1,2,3]`
**Output**: `null`
