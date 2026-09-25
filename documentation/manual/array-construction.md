# `[...]`

Array construction / collection. Inside `[...]` each expression (separated by commas) is evaluated and every result collected into a single array. If an inner expression emits multiple results, they are all included.

## Example 1

**Command**: `jq '[.user, .projects[]]'`
**Input**: `{"user":"stedolan", "projects":["jq","wikiflow"]}`
**Output**: `["stedolan", "jq", "wikiflow"]`

## Example 2

**Command**: `jq '[ .[] | . * 2 ]'`
**Input**: `[1,2,3]`
**Output**: `[2,4,6]`
