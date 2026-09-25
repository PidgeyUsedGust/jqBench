# `|`

The `|` operator combines two filters by feeding the output(s) of the one on the left into the input of the one on the right. If the left produces multiple results, the right runs for each of those results. Note that `.a.b.c` is the same as `.a | .b | .c`.

## Example 1

**Command**: `jq '.[] | .name'`
**Input**: `[{"name":"JSON", "good":true}, {"name":"XML", "good":false}]`
**Output**: `"JSON"` then `"XML"`
