# `.[start:end]`

Array/string slice. Returns a subarray or substring from `start` (inclusive) to `end` (exclusive). Either bound may be omitted; negative indices count from the end.

## Example 1

**Command**: `jq '.[2:4]'`
**Input**: `["a","b","c","d","e"]`
**Output**: `["c", "d"]`

## Example 2

**Command**: `jq '.[:3]'`
**Input**: `["a","b","c","d"]`
**Output**: `["a", "b", "c"]`

## Example 3

**Command**: `jq '.[-2:]'`
**Input**: `["a","b","c","d"]`
**Output**: `["c", "d"]`

## Example 4

**Command**: `jq '.[1:3]'`
**Input**: `"abcdef"`
**Output**: `"bc"`
