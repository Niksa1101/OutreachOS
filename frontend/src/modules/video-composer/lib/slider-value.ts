/**
 * Base UI's slider `onValueChange`/`onValueCommitted` type `value` as
 * `number | readonly number[]`, but TypeScript's built-in `Array.isArray`
 * type guard narrows to `any[]` regardless of the input's actual element
 * type (a long-standing `lib.es5` signature quirk) — so an indexed read
 * after the guard is silently `any` (eslint `no-unsafe-assignment`).
 * `Number(...)` coercion gives the read an explicit, non-`any` return type
 * without an unsafe cast.
 */
export function sliderValueAt(value: number | readonly number[], index: number): number {
  return Array.isArray(value) ? Number(value[index]) : Number(value);
}
