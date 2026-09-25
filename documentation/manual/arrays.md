# `arrays`

Passes through array inputs; suppresses others.

## Example 1

**Command**: `jq '[.[] | arrays]'`
**Input**: `[[],1]`
**Output**: `[[]]`
