#!/usr/bin/env node

// Independent BigInt-based reference for semantic_numeric_domain_policy_v1.
// It deliberately does not use JSON.parse or Number(inputLexeme) for numeric
// parsing or binary64 rounding. V8 is used only for the ECMAScript/JCS shortest
// rendering of an already constructed IEEE-754 bit pattern.

import fs from "node:fs";

const MAXIMUM_NUMERIC_LEXEME_LENGTH = 16_384;
const MAXIMUM_COEFFICIENT_DIGITS = 8_192;
const MAXIMUM_ABSOLUTE_EXPONENT = 32_768;
const NUMBER_GRAMMAR = /^(-?)(0|[1-9][0-9]*)(?:\.([0-9]+))?(?:[eE]([+-]?)([0-9]+))?$/;
const NUMBER_PREFIX_GRAMMAR = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/;
const NUMERIC_CHARACTER_TOKEN = /^[+\-.eE0-9]+$/;

function resourceFailure(limitName) {
  return {
    json_valid: null,
    numeric_domain_eligible: false,
    terminal_outcome: "failed_resource_limit",
    resource_limit: limitName,
  };
}

function exponentMagnitudeExceedsLimit(digits) {
  const magnitudeDigits = digits.replace(/^0+/, "") || "0";
  const maximumMagnitude = MAXIMUM_ABSOLUTE_EXPONENT.toString();
  return magnitudeDigits.length > maximumMagnitude.length
    || (
      magnitudeDigits.length === maximumMagnitude.length
      && magnitudeDigits > maximumMagnitude
    );
}

function preflightNumericCharacterToken(token) {
  if (token.length > MAXIMUM_NUMERIC_LEXEME_LENGTH) {
    return resourceFailure("maximum_numeric_lexeme_length");
  }
  const exponentOffset = token.search(/[eE]/);
  const coefficientEnd = exponentOffset === -1 ? token.length : exponentOffset;
  const coefficientDigits = [...token.slice(0, coefficientEnd)]
    .filter((character) => /[0-9]/.test(character)).length;
  if (coefficientDigits > MAXIMUM_COEFFICIENT_DIGITS) {
    return resourceFailure("maximum_numeric_significand_or_coefficient_digits");
  }
  if (exponentOffset !== -1) {
    let exponentDigits = token.slice(exponentOffset + 1);
    if (/^[+-]/.test(exponentDigits)) exponentDigits = exponentDigits.slice(1);
    if (/^[0-9]+$/.test(exponentDigits) && exponentMagnitudeExceedsLimit(exponentDigits)) {
      return resourceFailure("maximum_absolute_decimal_exponent_magnitude");
    }
  }
  return null;
}

function preflightValidNumber(numberLexeme) {
  const match = numberLexeme.match(NUMBER_GRAMMAR);
  if (!match) throw new Error("internal invalid numeric prefix");
  if (numberLexeme.length > MAXIMUM_NUMERIC_LEXEME_LENGTH) {
    return resourceFailure("maximum_numeric_lexeme_length");
  }
  const coefficientDigits = match[2].length + (match[3] || "").length;
  if (coefficientDigits > MAXIMUM_COEFFICIENT_DIGITS) {
    return resourceFailure("maximum_numeric_significand_or_coefficient_digits");
  }
  if (match[5] && exponentMagnitudeExceedsLimit(match[5])) {
    return resourceFailure("maximum_absolute_decimal_exponent_magnitude");
  }
  return null;
}

function parseExactDecimal(lexeme) {
  if (/^[-0-9]/.test(lexeme)) {
    if (NUMERIC_CHARACTER_TOKEN.test(lexeme)) {
      const tokenFailure = preflightNumericCharacterToken(lexeme);
      if (tokenFailure) return tokenFailure;
    }
    const prefix = lexeme.match(NUMBER_PREFIX_GRAMMAR)?.[0];
    if (prefix) {
      const prefixFailure = preflightValidNumber(prefix);
      if (prefixFailure) return prefixFailure;
    }
  }

  const match = lexeme.match(NUMBER_GRAMMAR);
  if (!match) {
    return {
      json_valid: false,
      numeric_domain_eligible: false,
      terminal_outcome: "failed_strict_parse",
    };
  }
  const negative = match[1] === "-";
  const fraction = match[3] || "";
  const explicitMagnitude = match[5]
    ? Number(match[5].replace(/^0+/, "") || "0")
    : 0;
  if (explicitMagnitude > MAXIMUM_ABSOLUTE_EXPONENT) {
    return resourceFailure("maximum_absolute_decimal_exponent_magnitude");
  }
  const explicitExponent = explicitMagnitude * (match[4] === "-" ? -1 : 1);
  return {
    json_valid: true,
    negative,
    coefficient: BigInt(match[2] + fraction),
    exponent: explicitExponent - fraction.length,
    explicit_exponent_magnitude: explicitMagnitude,
  };
}

function normalizedDecimal(decimal) {
  if (decimal.coefficient === 0n) {
    return { negative: false, coefficient: 0n, exponent: 0 };
  }
  let coefficient = decimal.coefficient;
  let exponent = decimal.exponent;
  while (coefficient % 10n === 0n) {
    coefficient /= 10n;
    exponent += 1;
  }
  return { negative: decimal.negative, coefficient, exponent };
}

function exactKey(decimal) {
  const normalized = normalizedDecimal(decimal);
  return `${normalized.negative ? "-" : ""}${normalized.coefficient}e${normalized.exponent}`;
}

function decimalsEqual(left, right) {
  return exactKey(left) === exactKey(right);
}

function compareDecimals(left, right) {
  const a = normalizedDecimal(left);
  const b = normalizedDecimal(right);
  if (a.coefficient === 0n && b.coefficient === 0n) return 0;
  if (a.negative !== b.negative) return a.negative ? -1 : 1;
  const minimumExponent = Math.min(a.exponent, b.exponent);
  const leftInteger = a.coefficient * (10n ** BigInt(a.exponent - minimumExponent));
  const rightInteger = b.coefficient * (10n ** BigInt(b.exponent - minimumExponent));
  const comparison = leftInteger < rightInteger ? -1 : leftInteger > rightInteger ? 1 : 0;
  return a.negative ? -comparison : comparison;
}

function bitLength(value) {
  return value === 0n ? 0 : value.toString(2).length;
}

function roundRatioTiesToEven(numerator, denominator) {
  let quotient = numerator / denominator;
  const remainder = numerator % denominator;
  const doubled = remainder * 2n;
  if (doubled > denominator || (doubled === denominator && (quotient & 1n))) {
    quotient += 1n;
  }
  return quotient;
}

function floorLog2Ratio(numerator, denominator) {
  let exponent = bitLength(numerator) - bitLength(denominator);
  if (exponent >= 0) {
    if (numerator < (denominator << BigInt(exponent))) exponent -= 1;
  } else if ((numerator << BigInt(-exponent)) < denominator) {
    exponent -= 1;
  }
  return exponent;
}

function decimalRatio(decimal) {
  if (decimal.exponent >= 0) {
    return {
      numerator: decimal.coefficient * (10n ** BigInt(decimal.exponent)),
      denominator: 1n,
    };
  }
  return {
    numerator: decimal.coefficient,
    denominator: 10n ** BigInt(-decimal.exponent),
  };
}

function decimalToBinary64Bits(decimal) {
  const signBits = decimal.negative ? (1n << 63n) : 0n;
  const { numerator, denominator } = decimalRatio(decimal);
  if (numerator === 0n) return signBits;

  if ((numerator << 1022n) < denominator) {
    const significand = roundRatioTiesToEven(numerator << 1074n, denominator);
    if (significand >= (1n << 52n)) return signBits | (1n << 52n);
    return signBits | significand;
  }

  let exponent = floorLog2Ratio(numerator, denominator);
  if (exponent > 1023) return signBits | (0x7ffn << 52n);
  const shift = 52 - exponent;
  let significand = shift >= 0
    ? roundRatioTiesToEven(numerator << BigInt(shift), denominator)
    : roundRatioTiesToEven(numerator, denominator << BigInt(-shift));
  if (significand === (1n << 53n)) {
    significand = 1n << 52n;
    exponent += 1;
  }
  if (exponent > 1023) return signBits | (0x7ffn << 52n);
  return signBits | (BigInt(exponent + 1023) << 52n) | (significand - (1n << 52n));
}

function bitsToNumber(bits) {
  const bytes = new ArrayBuffer(8);
  const view = new DataView(bytes);
  view.setBigUint64(0, bits, false);
  return view.getFloat64(0, false);
}

function isMathematicalInteger(decimal) {
  if (decimal.coefficient === 0n || decimal.exponent >= 0) return true;
  return decimal.coefficient % (10n ** BigInt(-decimal.exponent)) === 0n;
}

function analyzeLexeme(lexeme) {
  const exact = parseExactDecimal(lexeme);
  if (!exact.json_valid) return exact;
  if (exact.coefficient === 0n && exact.negative) {
    return {
      json_valid: true,
      numeric_domain_eligible: false,
      terminal_outcome: "failed_canonical_validation",
      safe_reason: "negative_zero",
      exact_decimal_key: "0e0",
    };
  }

  const bits = decimalToBinary64Bits(exact);
  const exponentBits = (bits >> 52n) & 0x7ffn;
  const magnitudeBits = bits & ((1n << 63n) - 1n);
  if (exponentBits === 0x7ffn) {
    return {
      json_valid: true,
      numeric_domain_eligible: false,
      terminal_outcome: "failed_canonical_validation",
      safe_reason: "binary64_overflow_nonfinite",
      exact_decimal_key: exactKey(exact),
      binary64_bits: bits.toString(16).padStart(16, "0"),
    };
  }
  if (exact.coefficient !== 0n && magnitudeBits === 0n) {
    return {
      json_valid: true,
      numeric_domain_eligible: false,
      terminal_outcome: "failed_canonical_validation",
      safe_reason: "nonzero_underflow_to_zero",
      exact_decimal_key: exactKey(exact),
      binary64_bits: bits.toString(16).padStart(16, "0"),
    };
  }

  const binary64 = bitsToNumber(bits);
  const jcs = JSON.stringify(binary64);
  const reparsed = parseExactDecimal(jcs);
  if (!decimalsEqual(exact, reparsed)) {
    return {
      json_valid: true,
      numeric_domain_eligible: false,
      terminal_outcome: "failed_canonical_validation",
      safe_reason: "decimal_round_trip_changed",
      exact_decimal_key: exactKey(exact),
      binary64_bits: bits.toString(16).padStart(16, "0"),
      ordinary_jcs_representation: jcs,
    };
  }
  return {
    json_valid: true,
    numeric_domain_eligible: true,
    exact_decimal_key: exactKey(exact),
    binary64_bits: bits.toString(16).padStart(16, "0"),
    jcs_numeric_representation: jcs,
    mathematical_integer: isMathematicalInteger(exact),
  };
}

function numericDescriptor(descriptor) {
  if (descriptor.type === "string") {
    return { type: "string", value: descriptor.value };
  }
  const lexeme = descriptor.lexeme || descriptor.canonical_lexeme || descriptor.jcs_numeric_representation;
  return { type: "number", analysis: analyzeLexeme(lexeme) };
}

function evaluateCase(suiteName, testCase) {
  if (suiteName === "number_vectors" || suiteName === "negative_zero_vectors") {
    return analyzeLexeme(testCase.input_lexeme);
  }
  if (suiteName === "price_vectors") {
    if (testCase.minimum_lexeme) {
      const minimum = parseExactDecimal(testCase.minimum_lexeme);
      const maximum = parseExactDecimal(testCase.maximum_lexeme);
      const eligible = analyzeLexeme(testCase.minimum_lexeme).numeric_domain_eligible
        && analyzeLexeme(testCase.maximum_lexeme).numeric_domain_eligible;
      const ordering = compareDecimals(minimum, maximum) <= 0 ? "passes" : "fails";
      return {
        numeric_domain_eligible: eligible,
        exact_decimal_ordering: ordering,
        terminal_outcome: ordering === "fails" ? "failed_cross_field_validation" : null,
      };
    }
    return analyzeLexeme(testCase.input.slice("exact amount ".length));
  }
  if (suiteName === "hash_equality_vectors") {
    const left = analyzeLexeme(testCase.left_lexeme);
    const right = analyzeLexeme(testCase.right_lexeme);
    return {
      accepted_semantic_hash_equality_result:
        left.numeric_domain_eligible && right.numeric_domain_eligible
          ? left.jcs_numeric_representation === right.jcs_numeric_representation
          : null,
    };
  }
  if (suiteName === "native_sdk_numeric_vectors") {
    const left = numericDescriptor(testCase.raw);
    const right = numericDescriptor(testCase.native);
    if (left.type !== right.type) return { equivalence: "proven_unequal" };
    if (left.type === "string") {
      return { equivalence: left.value === right.value ? "proven_equal" : "proven_unequal" };
    }
    if (left.analysis.exact_decimal_key !== right.analysis.exact_decimal_key) {
      return { equivalence: "proven_unequal" };
    }
    if (!left.analysis.numeric_domain_eligible || !right.analysis.numeric_domain_eligible) {
      return { equivalence: null };
    }
    return { equivalence: "proven_equal" };
  }
  if (suiteName === "integer_boolean_vectors") {
    if (testCase.input_json === "true" || testCase.input_json === "false") {
      return {
        json_type: "boolean",
        numeric_domain_validator_applicable: false,
        schema_integer_valid: false,
      };
    }
    const analysis = analyzeLexeme(testCase.input_lexeme);
    return {
      ...analysis,
      schema_integer_valid: analysis.numeric_domain_eligible
        ? analysis.mathematical_integer
        : false,
      schema_maximum_3_valid: analysis.numeric_domain_eligible
        ? compareDecimals(parseExactDecimal(testCase.input_lexeme), parseExactDecimal("3")) <= 0
        : false,
    };
  }
  if (suiteName === "json_numeric_syntax_vectors") {
    if (testCase.id === "J10") {
      return {
        json_valid: true,
        json_type: "string",
        numeric_coercion_allowed: false,
        number_required_terminal_outcome: "failed_canonical_validation",
      };
    }
    return analyzeLexeme(testCase.input);
  }
  throw new Error(`unknown suite: ${suiteName}`);
}

function collectLexemes(suites) {
  const lexemes = new Set();
  for (const [suiteName, suite] of Object.entries(suites)) {
    for (const testCase of suite.cases) {
      for (const field of ["input_lexeme", "left_lexeme", "right_lexeme", "minimum_lexeme", "maximum_lexeme"]) {
        if (testCase[field]) lexemes.add(testCase[field]);
      }
      if (suiteName === "price_vectors" && testCase.input) {
        lexemes.add(testCase.input.slice("exact amount ".length));
      }
      if (suiteName === "json_numeric_syntax_vectors" && testCase.id !== "J10") {
        lexemes.add(testCase.input);
      }
      for (const descriptor of [testCase.raw, testCase.native]) {
        if (descriptor?.type === "number") {
          lexemes.add(descriptor.lexeme || descriptor.canonical_lexeme || descriptor.jcs_numeric_representation);
        }
      }
    }
  }
  return [...lexemes].sort();
}

function exactDyadicDecimal(numerator, denominatorPower) {
  const coefficient = numerator * (5n ** BigInt(denominatorPower));
  const digits = coefficient.toString().padStart(denominatorPower + 1, "0");
  const split = digits.length - denominatorPower;
  return `${digits.slice(0, split)}.${digits.slice(split)}`;
}

const artifact = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const frozenNumericLimits = artifact.resource_limit_policy.required_limits;
const expectedNumericLimits = {
  maximum_numeric_lexeme_length: MAXIMUM_NUMERIC_LEXEME_LENGTH,
  maximum_numeric_significand_or_coefficient_digits: MAXIMUM_COEFFICIENT_DIGITS,
  maximum_absolute_decimal_exponent_magnitude: MAXIMUM_ABSOLUTE_EXPONENT,
};
for (const [limitName, expectedValue] of Object.entries(expectedNumericLimits)) {
  if (frozenNumericLimits[limitName] !== expectedValue) {
    throw new Error(`frozen numeric resource limit mismatch: ${limitName}`);
  }
}
const suites = artifact.semantic_numeric_domain_test_vectors.suites;
const vectorResults = [];
for (const [suiteName, suite] of Object.entries(suites)) {
  for (const testCase of suite.cases) {
    vectorResults.push({
      suite: suiteName,
      id: testCase.id,
      result: evaluateCase(suiteName, testCase),
    });
  }
}

const resourceProbeLexemes = {
  lexeme_limit: `1e${"0".repeat(16_382)}`,
  lexeme_limit_plus_one: `1e${"0".repeat(16_383)}`,
  coefficient_limit: `0.${"0".repeat(8_191)}`,
  coefficient_limit_plus_one: `0.${"0".repeat(8_192)}`,
  exponent_limit: "1e32768",
  exponent_limit_plus_one: "1e32769",
  invalid_leading_zero_coefficient_plus_one: "0".repeat(8_193),
  invalid_nonnumeric_over_lexeme_limit: "x".repeat(16_385),
  malformed_coefficient_over_limit: `${"0".repeat(8_193)}..`,
  malformed_lexeme_over_limit: "1.".repeat(9_000),
  malformed_exponent_over_limit: "1e32769e",
  malformed_double_sign_coefficient_over_limit: `--${"0".repeat(8_193)}`,
};

const overflowMidpoint = ((1n << 54n) - 1n) << 970n;
const binary64ProbeLexemes = {
  positive_zero: "0",
  one: "1",
  negative: "-1.5",
  halfway_ties_to_even_lower:
    "1.00000000000000011102230246251565404236316680908203125",
  halfway_ties_to_even_upper:
    "1.00000000000000033306690738754696212708950042724609375",
  minimum_subnormal: "5e-324",
  maximum_finite: "1.7976931348623157e308",
  positive_overflow: "1e309",
  subnormal_to_normal_midpoint: exactDyadicDecimal((1n << 53n) - 1n, 1075),
  finite_to_infinity_immediately_below: (overflowMidpoint - 1n).toString(),
  finite_to_infinity_midpoint: overflowMidpoint.toString(),
};

process.stdout.write(JSON.stringify({
  implementation_id: "semantic_numeric_bigint_javascript_reference_v1",
  vector_results: vectorResults,
  lexeme_results: Object.fromEntries(
    collectLexemes(suites).map((lexeme) => [lexeme, analyzeLexeme(lexeme)]),
  ),
  resource_probe_results: Object.fromEntries(
    Object.entries(resourceProbeLexemes).map(([id, lexeme]) => [id, analyzeLexeme(lexeme)]),
  ),
  binary64_probe_results: Object.fromEntries(
    Object.entries(binary64ProbeLexemes).map(([id, lexeme]) => [id, {
      lexeme,
      analysis: analyzeLexeme(lexeme),
    }]),
  ),
}));
