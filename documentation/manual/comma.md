# `,`

If two filters are separated by a comma, the same input is fed into both and the two filters' output streams are concatenated in order.

The `,` operator is one way to construct generators.

## Example 1

**Command**: `jq '.foo, .bar'`
**Input**: `{"foo": 42, "bar": "something else", "baz": true}`
**Output**: `42` then `"something else"`

## Example 2

**Command**: `jq '.user, .projects[]'`
**Input**: `{"user":"stedolan", "projects": ["jq", "wikiflow"]}`
**Output**: `"stedolan"` then `"jq"` then `"wikiflow"`

## Example 3

**Command**: `jq '.[4,2]'`
**Input**: `["a","b","c","d","e"]`
**Output**: `"e"` then `"c"`
