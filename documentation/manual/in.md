# `in`

Returns `true` if the (string or number) input is a key in the given object or an index in the given array, otherwise `false`. Usually used as `"key" in object` or `index in array`.

## Example 1

**Command**: `jq '"foo" in {"foo":1}'`
**Input**: `null`
**Output**: `true`

## Example 2

**Command**: `jq '2 in [10,11,12]'`
**Input**: `null`
**Output**: `true`

## Example 3

**Command**: `jq '3 in [10,11,12]'`
**Input**: `null`
**Output**: `false`
