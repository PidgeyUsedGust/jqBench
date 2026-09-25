# `try EXP catch HANDLER`

Error handling wrapper. Runs `EXP`; if it errors, the error message becomes input to `HANDLER` whose outputs are emitted instead.

## Example 1

**Command**: `jq 'try (error("boom")) catch .'`
**Input**: `null`
**Output**: `"boom"`
