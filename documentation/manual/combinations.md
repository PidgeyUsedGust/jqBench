# `combinations`

Generates all combinations by taking one element from each subarray of the input array of arrays.

## Example 1

**Command**: `jq 'combinations'`
**Input**: `[[1,2],["a","b"]]`
**Output**: `[1,"a"]` then `[1,"b"]` then `[2,"a"]` then `[2,"b"]`

## Example 2 (three dimensions)

**Command**: `jq 'combinations'`
**Input**: `[[1],["x","y"],[true,false]]`
**Output**: `[1,"x",true]` then `[1,"x",false]` then `[1,"y",true]` then `[1,"y",false]`
