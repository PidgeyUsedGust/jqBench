# `..`

Recursive descent. Emits every value reachable by recursively walking arrays and objects from the input. Equivalent to `recurse` with no arguments. Combine with selectors to pick nested values.

## Example 1

**Command**: `jq '.. | .a?'`
**Input**: `[[{"a":1}]]`
**Output**: `1`
