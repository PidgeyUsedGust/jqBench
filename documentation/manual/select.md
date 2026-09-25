# `select(cond)`

Evaluates `cond` for each input value; if truthy the original value is passed through, otherwise it is filtered out (no output). Similar to `grep` for JSON.

## Example 1

**Command**: `jq '.[] | select(.active)'`
**Input**: `[{"id":1,"active":true},{"id":2,"active":false}]`
**Output**: `{"id":1,"active":true}`

## Example 2

**Command**: `jq '.[] | select(.score > 10)'`
**Input**: `[{"score":5},{"score":12}]`
**Output**: `{"score":12}`
