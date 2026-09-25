# `map`

Applies `expr` to each element of the input array, collecting results into a new array. For object value mapping see `map_values`.

## Example 1

**Command**: `jq 'map(. * 2)'`
**Input**: `[1,2,3]`
**Output**: `[2,4,6]`

## Example 2

**Command**: `jq 'map_values(.+1)'`
**Input**: `{"a":1,"b":2}`
**Output**: `{"a":2,"b":3}`
