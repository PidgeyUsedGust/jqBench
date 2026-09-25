# `bsearch(x)`

Binary search for `x` in a sorted array input; returns index or null.

## Example 1

**Command**: `jq 'bsearch(3)'`
**Input**: `[1,3,5]`
**Output**: `1`

## Example 2 (not found)

**Command**: `jq 'bsearch(2)'`
**Input**: `[1,3,5]`
**Output**: `null`
