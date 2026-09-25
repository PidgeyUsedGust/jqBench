# `unique_by(expr)`

Removes duplicates comparing keys from `expr`.

## Example 1

**Command**: `jq 'unique_by(.id)'`
**Input**: `[{"id":1},{"id":1},{"id":2}]`
**Output**: `[{"id":1},{"id":2}]`
