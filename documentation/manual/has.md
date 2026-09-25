# `has(key)`

Returns true if the input object has the given key, or the input array has an element at that index. Faster than computing `keys` and searching.

## Example 1

**Command**: `jq 'map(has("foo"))'`
**Input**: `[{"foo":42}, {}]`
**Output**: `[true, false]`

## Example 2

**Command**: `jq 'map(has(2))'`
**Input**: `[[0,1], ["a","b","c"]]`
**Output**: `[false, true]`
