# `@html`

HTML-escapes special characters (`&`, `<`, `>`, `"`) in the input string.

## Example 1

**Command**: `jq '@html'`
**Input**: `"<b>&"`
**Output**: `"&lt;b&gt;&amp;"`
