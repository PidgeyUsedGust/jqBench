# `range`

Generates integer sequences. Forms: `range(n)`, `range(from; to)`, `range(from; to; step)`.

## Example 1

**Command**: `jq '[range(5)]'`
**Input**: `null`
**Output**: `[0,1,2,3,4]`

## Example 2

**Command**: `jq '[range(2;6)]'`
**Input**: `null`
**Output**: `[2,3,4,5]`

## Example 3

**Command**: `jq '[range(10;5;-2)]'`
**Input**: `null`
**Output**: `[10,8,6]`
