# `skip(n; stream)`

Discards first `n` values produced by `stream`, passing the rest.

## Example 1

**Command**: `jq '[skip(2; range(5))]'`
**Input**: `null`
**Output**: `[2,3,4]`

## Example 2 (skip 0)

**Command**: `jq '[skip(0; range(4))]'`
**Input**: `null`
**Output**: `[0,1,2,3]`

## Example 3 (skip beyond length)

**Command**: `jq '[skip(10; range(3))]'`
**Input**: `null`
**Output**: `[]`
