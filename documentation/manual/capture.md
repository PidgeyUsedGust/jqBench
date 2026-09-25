# `capture(regex; flags?)`

Parses named capture groups in the first regex match into an object mapping group names to matched strings.

## Example 1

**Command**: `jq 'capture("(?<k>[a-z]+)(?<n>[0-9]+)")'`
**Input**: `"abc123"`
**Output**: `{"k":"abc","n":"123"}`
