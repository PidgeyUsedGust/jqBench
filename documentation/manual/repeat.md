# `repeat(expr)`

Evaluates `expr` repeatedly starting from the current input and emits each result until `expr` fails or produces no further output. Commonly combined with filters like `select` or `limit` to stop.

## Example 1

**Command**: `jq '1 | repeat(.+1) | select(.<5)'`
**Input**: `null`
**Output**: `2` then `3` then `4`
