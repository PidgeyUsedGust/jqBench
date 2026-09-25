# `@sh`

Shell-escapes a string for safe use in POSIX shell single-quoted context (wraps and escapes single quotes properly).

## Example 1

**Command**: `jq '@sh'`
**Input**: `"O'Reilly"`
**Output**: `"'O'\''Reilly'"`
