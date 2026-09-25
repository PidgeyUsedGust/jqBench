# `map_values(expr)`

Applies `expr` to each value of the input object, preserving keys.

## Example 1

**Command**: `jq 'map_values(.+1)'`
**Input**: `{"a":1,"b":2}`
**Output**: `{"a":2,"b":3}`
