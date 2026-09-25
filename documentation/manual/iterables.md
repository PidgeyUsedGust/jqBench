# `iterables`

Passes arrays and objects.

## Example 1

**Command**: `jq '[.[] | iterables]'`
**Input**: `[[],{},1]`
**Output**: `[[],{}]`
