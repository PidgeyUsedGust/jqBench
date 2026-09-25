# `min_by(expr)`

Returns element with minimum key per `expr`.

## Example 1

**Command**: `jq 'min_by(.age)'`
**Input**: `[{"age":30},{"age":25}]`
**Output**: `{"age":25}`
