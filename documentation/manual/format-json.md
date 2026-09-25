# `@json`

Outputs the JSON-encoded string form of the input value (escaping within a JSON string). Equivalent to `tojson | @text` conceptually.

## Example 1

**Command**: `jq '@json'`
**Input**: `{"a":1}`
**Output**: `"{\"a\":1}"`
