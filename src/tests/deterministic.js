// GeoBench: deterministic request parameter helpers for fair cross-server runs.

function mix32(value) {
  var x = value | 0;
  x = Math.imul(x ^ (x >>> 16), 0x85ebca6b);
  x = Math.imul(x ^ (x >>> 13), 0xc2b2ae35);
  return (x ^ (x >>> 16)) >>> 0;
}

export function deterministicSeed(salt) {
  var vu = typeof __VU === "number" ? __VU : 0;
  var iter = typeof __ITER === "number" ? __ITER : 0;
  var seed =
    ((vu + 1) * 73856093) ^
    ((iter + 1) * 19349663) ^
    (salt || 0);
  return mix32(seed);
}

export function deterministicUnit(salt) {
  return deterministicSeed(salt) / 4294967296;
}

export function deterministicInt(maxExclusive, salt) {
  if (!maxExclusive || maxExclusive <= 0) {
    return 0;
  }
  return Math.floor(deterministicUnit(salt) * maxExclusive);
}

export function deterministicChoice(values, salt) {
  return values[deterministicInt(values.length, salt)];
}

export function deterministicRange(min, max, salt) {
  return min + deterministicUnit(salt) * (max - min);
}
