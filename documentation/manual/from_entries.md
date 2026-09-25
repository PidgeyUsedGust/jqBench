# `from_entries`

Inverse of `to_entries`: turns an array of `{key, value}` objects into an object.

## Example 1

**Command**: `jq 'from_entries'`
**Input**: `[{"key":"a","value":1},{"key":"b","value":2}]`
**Output**: `{"a":1,"b":2}`
