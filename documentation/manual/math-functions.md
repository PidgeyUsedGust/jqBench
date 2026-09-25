# Math functions

Unary, binary and ternary math functions.

- Unary: `acos acosh asin asinh atan atanh cbrt ceil cos cosh erf erfc exp exp10 exp2 expm1 fabs floor gamma j0 j1 lgamma log log10 log1p log2 logb nearbyint rint round significand sin sinh sqrt tan tanh tgamma trunc y0 y1`
- Binary: `atan2 copysign drem fdim fmax fmin fmod frexp hypot jn ldexp modf nextafter nexttoward pow remainder scalb scalbln yn`
- Ternary: `fma`

All consume numeric inputs (or arrays via mapping) and output numeric results.

## Example 1

**Command**: `jq 'sqrt'`
**Input**: `9`
**Output**: `3`

## Example 2

**Command**: `jq 'pow'`
**Input**: `[2,8]`
**Output**: `256`
