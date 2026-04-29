// Shared duration parsing for k6 scenario start-time math.

export function durationToSeconds(value) {
  var text = String(value || "0s").trim().toLowerCase();
  var match = text.match(/^([0-9]+(?:\.[0-9]+)?)(ms|s|m|h)?$/);
  if (!match) {
    throw new Error("Unsupported duration value: " + value);
  }

  var amount = parseFloat(match[1]);
  var unit = match[2] || "s";
  if (unit === "ms") {
    return amount / 1000;
  }
  if (unit === "s") {
    return amount;
  }
  if (unit === "m") {
    return amount * 60;
  }
  if (unit === "h") {
    return amount * 3600;
  }

  throw new Error("Unsupported duration unit: " + unit);
}
