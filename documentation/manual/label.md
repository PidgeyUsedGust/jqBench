# `label $name` and `break $name`

Named labels allow breaking out of control structures. Use `label $name | ... break $name ...`. `break $name` acts as if the nearest `label $name` produced `empty`. The relationship is lexical; the label must be visible from the break.

## Example 1

```jq
label $out | reduce .[] as $item (null; if .==false then break $out else ... end)
```

Attempting `break $out` without a visible label produces a syntax error.
