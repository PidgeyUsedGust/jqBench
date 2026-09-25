# `{...}`

Object construction. Keys may be identifier-like (unquoted) or any expression in parentheses. Values are expressions applied to the input. Missing shorthand `{a, b}` expands to `{a: .a, b: .b}`.

If a value expression emits multiple results, multiple objects are emitted (one per value result). Variable names used as keys without a value mean `{var: $var}`.

## Example 1

**Command**: `jq '{user, title: .titles[]}'`
**Input**: `{"user":"stedolan","titles":["JQ Primer","More JQ"]}`
**Output**: `{"user":"stedolan","title":"JQ Primer"}` then `{"user":"stedolan","title":"More JQ"}`

## Example 2

**Command**: `jq '{(.user): .titles}'`
**Input**: `{"user":"stedolan","titles":["JQ Primer","More JQ"]}`
**Output**: `{"stedolan":["JQ Primer","More JQ"]}`
