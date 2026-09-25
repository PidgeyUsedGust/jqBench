# `isfinite`

Returns true if the input number is finite.

## Example 1

**Command**: `jq 'map(isfinite)'`
**Input**: `[1, (1/0)]`
**Output**: `[true,false]`
