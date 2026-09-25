# `@text`

Renders the input as raw text: strings without surrounding quotes / escapes; for other types their JSON form.

## Example 1

**Command**: `jq '@text'`
**Input**: `"line\nfeed"`
**Output**: `"line
feed"`
