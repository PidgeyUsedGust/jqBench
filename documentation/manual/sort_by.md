# `sort_by(expr)`

Sorts array by the key produced from each element by `expr`.

## Example 1

**Command**: `jq 'sort_by(.age)'`
**Input**: `[{"age":30},{"age":25}]`
**Output**: `[{"age":25},{"age":30}]`
