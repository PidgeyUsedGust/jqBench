# `abs`

Absolute value (naive definition: `if . < 0 then - . else . end`). For numeric input, yields the absolute value while preserving jq's literal form when untouched by other arithmetic.

## Example 1

**Command**: `jq 'map(abs)'`
**Input**: `[-10, -1.1, -1e-1]`
**Output**: `[10,1.1,1e-1]`
