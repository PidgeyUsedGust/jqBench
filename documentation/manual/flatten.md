# `flatten(n?)`

Flattens nested arrays to depth `n` (or fully if omitted).

## Example 1

**Command**: `jq 'flatten'`
**Input**: `[1,[2,[3]]]`
**Output**: `[1,2,3]`

## Example 2

**Command**: `jq 'flatten(1)'`
**Input**: `[1,[2,[3]]]`
**Output**: `[1,2,[3]]`

## Example 3 (depth 0 no change)

**Command**: `jq 'flatten(0)'`
**Input**: `[1,[2,[3]]]`
**Output**: `[1,[2,[3]]]`

## Example 4 (empty array)

**Command**: `jq 'flatten'`
**Input**: `[]`
**Output**: `[]`
