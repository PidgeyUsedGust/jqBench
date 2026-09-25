# `while(cond; update)`

Emits successive values while `cond` holds; after each emission applies `update` to produce the next value.

## Example 1

**Command**: `jq '0 | while(.<3; .+1)'`
**Input**: `null`
**Output**: `0` then `1` then `2`
