# `.foo?`

Optional object identifier index. Like `.foo` but suppresses errors when the input is not an object; produces `null` instead (and when iterated inside arrays, missing values simply vanish if further filtered).

## Example 1

**Command**: `jq '.foo?'`
**Input**: `{"foo": 42}`
**Output**: `42`

## Example 2

**Command**: `jq '.foo?'`
**Input**: `{"bar": 1}`
**Output**: `null`

## Example 3

**Command**: `jq '[.[] | .a?]'`
**Input**: `[{}, {"a":1}]`
**Output**: `[1]`
