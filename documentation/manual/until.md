# `until(cond; next)`

Applies `next` repeatedly, starting from the input, until `cond` evaluates to true for the current value; then emits that value.

## Example 1

**Command**: `jq '0 | until(.>5; .+2)'`
**Input**: `null`
**Output**: `6`
