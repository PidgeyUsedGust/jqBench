# `/`

Division of numbers. Dividing a string by another splits the first using the second as separators.

See also `*` and `%`.

## Example 1

**Command**: `jq '10 / . * 3'`
**Input**: `5`
**Output**: `6`

## Example 2

**Command**: `jq '. / ", "'`
**Input**: `"a, b,c,d, e"`
**Output**: `["a","b,c,d","e"]`
