# `recurse(f?)`

Recursively emits values by repeatedly applying optional step filter `f` (default: descend into array/object children). Equivalent to `..` when no argument.

## Example 1

**Command**: `jq 'recurse | select(type=="number")'`
**Input**: `{"a":[1,{"b":2}]}`
**Output**: `1` then `2`

## Example 2 (custom step filter on tree)

**Command**: `jq 'recurse(.children[]?) | .name? // empty'`
**Input**: `{"name":"root","children":[{"name":"a"},{"name":"b","children":[{"name":"c"}]}]}`
**Output**: `"root"` then `"a"` then `"b"` then `"c"`
