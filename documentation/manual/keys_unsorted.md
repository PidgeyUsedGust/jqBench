# `keys_unsorted`

Like `keys` but for objects preserves (approximate) insertion order instead of sorting. For arrays identical to `keys`.

## Example 1

**Command**: `jq 'keys_unsorted'`
**Input**: `{"b":1, "a":2}`
**Output**: `["b","a"]`
