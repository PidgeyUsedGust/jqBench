# `max_by(expr)`

Returns element with maximum key per `expr`.

## Example 1

**Command**: `jq 'max_by(.age)'`
**Input**: `[{"age":30},{"age":25}]`
**Output**: `{"age":30}`
