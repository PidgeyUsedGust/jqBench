# `contains(sub)`

For strings: `true` if the string contains `sub`. For arrays: every element of `sub` appears in the array. For objects: every key/value in `sub` appears in the input object (recursively). Otherwise `false`.

## Example 1

**Command**: `jq 'contains("bc")'`
**Input**: `"abcd"`
**Output**: `true`

## Example 2

**Command**: `jq 'contains([2,3])'`
**Input**: `[1,2,3,4]`
**Output**: `true`

## Example 3

**Command**: `jq 'contains({"a":1})'`
**Input**: `{"a":1, "b":2}`
**Output**: `true`
