# `label $name` / `break $name`

Defines a label to allow breaking out of nested recursion / loops. `break $name` aborts output and unwinds to after the label.

## Example 1

**Command**: `jq 'label $out | range(10) | if .==3 then break $out else . end'`
**Input**: `null`
**Output**: `0` then `1` then `2`
