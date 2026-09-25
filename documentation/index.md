# jq Manual Index

List of documented jq entities grouped by category. Format:

- name (`signature`): description

## Core

- identity (`.`): The identity filter.
- type (`type`): Outputs a string describing the type of the input: one of `"null"`, `"boolean"`, `"number"`, `"string"`, `"array"`, `"object"`.

## Type Filters

- nulls (`nulls`): Passes null inputs.
- booleans (`booleans`): Passes boolean inputs.
- numbers (`numbers`): Passes numeric inputs.
- strings (`strings`): Passes string inputs.
- arrays (`arrays`): Passes through array inputs; suppresses others.
- objects (`objects`): Passes through object inputs.
- scalars (`scalars`): Passes non-iterables: null, booleans, numbers, strings.
- values (`values`): Passes any input that is not `null`.
- iterables (`iterables`): Passes arrays and objects.

## Construction & Indexing

- array-construction (`[...]`): Array construction / collection.
- object-construction (`{...}`): Object construction.
- array-index (`.[<number>]`): Array index.
- object-identifier-index (`.foo`): Object identifier index.
- object-index (`.[<string>]`): Bracket object index.
- optional-object-identifier-index (`.foo?`): Optional object identifier index.
- optional (`?`): The `?` operator, used as `EXP?`, is shorthand for `try EXP`.
- range (`range`): Generates integer sequences.
- slice (`.[start:end]`): Array/string slice.
- nth (`nth(n; expr?)`): The `nth(n)` function extracts the nth value of any array at `.`.
- from_entries (`from_entries`): Inverse of `to_entries`: turns an array of `{key, value}` objects into an object.
- to_entries (`to_entries`): Converts an object to an array of `{key, value}` objects.
- with_entries (`with_entries(expr)`): Transforms each `{key, value}` pair of an object by mapping through `expr` (which receives `{key, value}`) then reassembling.

## Paths & Streams

- path (`path(expr)`): Emits the path (as an array of keys/indices) to each value produced by `expr` from the current input.
- paths (`paths`): Without arguments, emits every path to values in the input.
- getpath (`getpath(pathArray)`): Returns value at given path array (e.g.
- addpath (`addpath(pathArray)`): Ensures path exists, creating objects/arrays; returns modified input.
- setpath (`setpath(pathArray; value)`): Sets value at path, creating intermediate containers.
- del (`del(path_expression)`): Deletes the field(s)/element(s) at the given path(s).
- delpaths (`delpaths(paths_array)`): Deletes all paths listed (each path is an array of keys/indices).
- pick (`pick(pathexprs)`): Projects input object/array keeping only specified paths.
- tostream (`tostream`): Emits a stream of `[path, value]` arrays representing every leaf and intermediate node in the input JSON structure.
- fromstream (`fromstream(stream)`): Reconstructs a JSON value from a stream of `[path,value]` arrays produced by `tostream`.
- truncate_stream (`truncate_stream(stream)`): Truncates path elements from a stream of `[path, value]` pairs (as from `tostream`).

## Iteration & Recursion

- value-iterator (`.[]`): Array / object value iterator.
- value-iterator-optional (`.[]?`): Optional value iterator.
- recurse (`recurse(f?)`): Recursively emits values by repeatedly applying optional step filter `f` (default: descend into array/object children).
- recursive-descent (`..`): Recursive descent.
- walk (`walk(f)`): Recursively applies function `f` to every child value, rebuilding the structure.
- map (`map`): Applies `expr` to each element of the input array, collecting results into a new array.
- map_values (`map_values(expr)`): Applies `expr` to each value of the input object, preserving keys.
- foreach (`foreach stream as $var (init; update; extract?)`): Iterates like `reduce`, but can emit intermediate values.

## Selection & Testing

- select (`select(cond)`): Evaluates `cond` for each input value; if truthy the original value is passed through, otherwise it is filtered out (no output).
- contains (`contains(sub)`): For strings: `true` if the string contains `sub`.
- inside (`inside(x)`): Returns `true` if input is contained within `x` (reverse of `contains`).
- isempty (`isempty(stream)`): Returns `true` if `stream` produces no values, else `false`.
- any (`any`): Forms: `any(stream)` or `any(stream; cond)`.
- all (`all`): Forms: `all(stream)` or `all(stream; cond)`.
- has (`has(key)`): Returns true if the input object has the given key, or the input array has an element at that index.
- in (`in`): Returns `true` if the (string or number) input is a key in the given object or an index in the given array, otherwise `false`.
- index (`index(x)`): Returns first index of substring / element `x` or `null`.
- indices (`indices(x)`): Returns array of all indices where `x` occurs.
- rindex (`rindex(x)`): Returns last index of substring / element `x` or `null`.
- regex-test (`test(regex; flags?)`): Returns `true` if the input string matches the regular expression.
- scan (`scan(regex; flags?)`): Emits a match object for each non-overlapping regex match.
- match (`match(regex; flags?)`): Returns a match object for the first regex match in the input string.
- startswith (`startswith(str)`): Returns `true` if the input string begins with `str`.
- endswith (`endswith(str)`): Returns `true` if the input string ends with `str`.
- bsearch (`bsearch(x)`): Binary search for `x` in a sorted array input; returns index or null.
- capture (`capture(regex; flags?)`): Parses named capture groups in the first regex match into an object mapping group names to matched strings.

## String Functions

- split (`split(sep)`): Splits the input string on the given separator string (or regex if used with `test`/`match` functions separately) into an array of substrings.
- splits (`splits(regex; flags?)`): Generator version of `split`; emits substrings separated by regex matches.
- join (`join(sep)`): For an array of strings, concatenates them inserting `sep` between elements.
- explode (`explode`): Converts a string to an array of Unicode codepoint numbers.
- implode (`implode`): Converts an array of Unicode codepoint numbers to a string.
- gsub (`gsub(regex; replacement; flags?)`): Like `sub` but replaces all matches.
- sub (`sub(regex; replacement; flags?)`): Replaces the first match of `regex` with `replacement` (which may interpolate captures using `\(.name)`).
- ltrim (`ltrim`): Removes leading ASCII whitespace.
- ltrimstr (`ltrimstr(str)`): Removes the prefix `str` if present.
- rtrim (`rtrim`): Removes trailing ASCII whitespace.
- rtrimstr (`rtrimstr(str)`): Removes the suffix `str` if present.
- trim (`trim`): Removes leading and trailing ASCII whitespace.
- trimstr (`trimstr(str)`): Removes matching prefix and suffix `str` if both present.
- ascii_downcase (`ascii_downcase`): Converts ASCII letters to lowercase.
- ascii_upcase (`ascii_upcase`): Converts ASCII letters to uppercase.
- utf8bytelength (`utf8bytelength`): Outputs the number of UTF‑8 bytes needed to encode the input string.
- tostring (`tostring`): Converts value to string representation.
- tojson (`tojson`): Converts value to JSON-encoded string.
- fromjson (`fromjson`): Parses a JSON-encoded string into a value.
- toboolean (`toboolean`): Converts certain strings (case-insensitive `true`, `false`) to booleans; passes booleans unchanged; errors on other values.
- tonumber (`tonumber`): Parses a numeric string to a number.

## Formatting & Encoding

- format-csv (`@csv`): Formats the input array of strings (or values coercible to strings) as a single CSV record string (RFC 4180 style quoting) and outputs that string.
- format-tsv (`@tsv`): Formats an array of strings as a single tab-separated record with necessary escaping.
- format-html (`@html`): HTML-escapes special characters (`&`, `<`, `>`, `"`) in the input string.
- format-json (`@json`): Outputs the JSON-encoded string form of the input value (escaping within a JSON string).
- format-sh (`@sh`): Shell-escapes a string for safe use in POSIX shell single-quoted context (wraps and escapes single quotes properly).
- format-text (`@text`): Renders the input as raw text: strings without surrounding quotes / escapes; for other types their JSON form.
- format-uri (`@uri`): Percent-encodes the input string as a URI component.
- base64 (`@base64`): Encodes string (or JSON representation of non-string) to base64.
- base64d (`@base64d`): Decodes a base64 string.

## Aggregation, Reduction & Ordering

- reduce (`reduce stream as $var (init; update)`): Folds the results of `stream` into an accumulator starting at `init`.
- add (`add`): For an array of numbers, strings or arrays/objects, folds them with `+`.
- group_by (`group_by(expr)`): Groups a sorted array into subarrays where `expr` yields equal keys.
- limit (`limit(n; stream)`): Passes through at most `n` results from `stream` and then stops.
- skip (`skip(n; stream)`): Discards first `n` values produced by `stream`, passing the rest.
- first (`first(stream?)`): Returns the first value produced by its input or by the `stream` expression, if any.
- last (`last(stream?)`): Returns the last value produced by its input or by `stream`.
- length (`length`): Length of strings (Unicode codepoints), arrays (element count), objects (key count), `null` (0), numbers (absolute value).
- transpose (`transpose`): Matrix transpose: converts array-of-arrays rows into columns.
- flatten (`flatten(n?)`): Flattens nested arrays to depth `n` (or fully if omitted).
- reverse (`reverse`): Reverses an array.
- sort (`sort`): Sorts an array of numbers or strings.
- sort_by (`sort_by(expr)`): Sorts array by the key produced from each element by `expr`.
- unique (`unique`): Removes duplicate elements from a sorted array.
- unique_by (`unique_by(expr)`): Removes duplicates comparing keys from `expr`.
- min (`min`): Returns minimum element of an array.
- max (`max`): Returns maximum element of an array.
- min_by (`min_by(expr)`): Returns element with minimum key per `expr`.
- max_by (`max_by(expr)`): Returns element with maximum key per `expr`.
- combinations (`combinations`): Generates all combinations by taking one element from each subarray of the input array of arrays.

## Math & Numeric

- abs (`abs`): Absolute value (naive definition: `if . < 0 then - . else . end`).
- sqrt (`sqrt`): Square root of the input number.
- math-functions (`Math functions`): Unary, binary and ternary math functions.

## Time & Date

- time-fromdateiso8601 (`fromdateiso8601`): Parses an ISO 8601 date/time string (UTC or with offset) into epoch seconds.
- time-gmtime (`gmtime`): Converts an epoch time (seconds since 1970-01-01 UTC) number to a UTC broken-down time array `[year,month,day,hour,minute,second]` (month 1-12, day 1-31).
- time-localtime (`localtime`): Converts epoch seconds to a broken-down local time array `[year,month,day,hour,minute,second]` using system timezone.
- time-mktime (`mktime`): Inverse of `localtime`/`gmtime`.
- time-now (`now`): Returns the current time as a (possibly fractional) number of seconds since the Unix epoch.
- time-strftime (`strftime(fmt)`): Formats a broken-down time array according to POSIX `strftime` format string.
- time-strptime (`strptime(fmt)`): Parses a date/time string using the given format into a broken-down time array.
- time-todateiso8601 (`todateiso8601`): Formats an epoch seconds number as an ISO 8601 UTC timestamp string.

## Control Flow & Variables

- if-then-else (`if C then A else B end`): Conditional execution.
- try-catch (`try EXP catch HANDLER`): Error handling wrapper.
- repeat (`repeat(expr)`): Evaluates `expr` repeatedly starting from the current input and emits each result until `expr` fails or produces no further output.
- until (`until(cond; next)`): Applies `next` repeatedly, starting from the input, until `cond` evaluates to true for the current value; then emits that value.
- while (`while(cond; update)`): Emits successive values while `cond` holds; after each emission applies `update` to produce the next value.
- label (`label $name`): Named labels allow breaking out of control structures.
- label-break (`label $name`): Defines a label to allow breaking out of nested recursion / loops.
- as-variable (`as $var`): Binds the result of an expression to a variable for use downstream in the pipeline.
- assignment-update (`Assignment / update: `=`, `|=`, `+=`, `-=`, `*=`, `/=`, `%=``): Used with paths on the left-hand side.
- error (`error(message?)`): Raises an error optionally with a message; aborts filter unless caught with `try`.
- debug (`debug`): Writes the input (with prefix) to stderr, then passes it through unchanged.
- stderr (`stderr(value)`): Writes `value` to stderr and returns the original input.

## Operators & Logic

- plus (`+`): The operator `+` takes two filters, applies them both to the same input, and adds the results together.
- minus (`-`): As well as normal arithmetic subtraction on numbers, the `-` operator can be used on arrays to remove all occurrences of the second array's elements from the first array.
- star (`*`): When applied to numbers, `*` multiplies.
- divide (`/`): Division of numbers.
- modulo (`%`): Modulo of numbers: `x % y` computes x modulo y.
- alternative (`//`): The `//` operator produces all the values of its left-hand side that are neither `false` nor `null`; if none, it produces the values of its right-hand side.
- comma (`,`): If two filters are separated by a comma, the same input is fed into both and the two filters' output streams are concatenated in order.
- pipe (`|`): The `|` operator combines two filters by feeding the output(s) of the one on the left into the input of the one on the right.
- parenthesis (`Parenthesis`): Parentheses group expressions and control evaluation order, just like in other languages.
- equals (`==`): The expression `a == b` produces `true` if evaluating `a` and `b` yields equivalent JSON values and `false` otherwise.
- not-equals (`!=`): `a != b` returns the opposite of `a == b`.
- lt (`<`): Strictly less-than comparison.
- lte (`<=`): Less-than-or-equal comparison.
- gt (`>`): Strictly greater-than comparison.
- gte (`>=`): Greater-than-or-equal comparison.
- and (`and`): Logical conjunction of its left and right operands using jq truthiness.
- or (`or`): Logical disjunction; if left is truthy it is returned, else right is evaluated.
- not (`not`): Logical negation of jq truthiness.

## Special Values

- nan (`nan`): Produces IEEE NaN.
- infinite (`infinite`): Produces positive infinity.
- finites (`finites`): Stream selector passing only finite numbers.
- isfinite (`isfinite`): Returns true if the input number is finite.
- isinfinite (`isinfinite`): Returns true if the input number is infinite.
- isnan (`isnan`): Returns true if the input number is NaN.
- isnormal (`isnormal`): Returns true if the input number is a normal (not subnormal, inf, NaN) float.
- normals (`normals`): Stream selector passing only normal floating-point numbers.

## Uncategorized

- empty (`empty`): Produces no output (used to filter out values).
- keys (`keys`): For objects, returns an alphabetically (Unicode codepoint) sorted array of keys.
- keys_unsorted (`keys_unsorted`): Like `keys` but for objects preserves (approximate) insertion order instead of sorting.
