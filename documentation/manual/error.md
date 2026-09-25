# `error(message?)`

Raises an error optionally with a message; aborts filter unless caught with `try`.

## Example 1

**Command**: `jq 'try error("boom") catch ."'`
**Input**: `null`
**Output**: `"boom"`
