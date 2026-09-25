# `.[]`

Array / object value iterator. For an array, emits each element as a separate output. For an object, emits each value. A form like `.foo[]` is equivalent to `.foo | .[]`.

## Example 1

**Command**: `jq '.[]'`
**Input**: `[1,2,3]`
**Output**: `1` then `2` then `3`

## Example 2

**Command**: `jq '.[]'`
**Input**: `{ "a":1, "b":2 }`
**Output**: `1` then `2`

## Example 3

**Command**: `jq '.foo[]'`
**Input**: `{"foo":["x","y"]}`
**Output**: `"x"` then `"y"`
