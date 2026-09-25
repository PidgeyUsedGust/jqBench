# `paths`, `paths(expr)`

Without arguments, emits every path to values in the input. With `expr`, emits only paths whose target values make `expr` truthy.

## Example 1

**Command**: `jq 'paths'`
**Input**: `[1,{"a":2}]`
**Output**: `[0]` then `[1]` then `[1,"a"]`

## Example 2

**Command**: `jq 'paths(.==2)'`
**Input**: `[1,{"a":2}]`
**Output**: `[1,"a"]`
