# `if C then A else B end`

Conditional execution. Evaluates `C`; if truthy, executes filter `A` producing its outputs; otherwise executes filter `B`. `elif` can be expressed via nested `if` or by using alternative conditionals.

## Example 1

**Command**: `jq 'if . > 2 then "big" else "small" end'`
**Input**: `3`
**Output**: `"big"`
