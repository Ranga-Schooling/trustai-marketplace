#!/usr/bin/env node

/*
 * Independent executable reference for canonical_parser_policy_json_v1.
 *
 * This intentionally does not import application identity code or use
 * JSON.parse/JSON.stringify for parsing or canonical serialization.  It is a
 * second implementation of the frozen normalization-spec identity contract.
 */

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

const SAFE_INTEGER = 9007199254740991n;
const SHA256 = /^[0-9a-f]{64}$/u;
const EXPECTED_PROMPT_HASH =
  "9d6c5e43acb971b3ffb2a47b69f0def142d21c971717541e007f711404603df2";
const EXPECTED_SCHEMA_HASH =
  "125809d08e911d51b4619002f02a969b03b8da5866bfab1b8346758c0bb9a6f4";

const BINDINGS = [
  ["attempt_run_outcome_model_v1", "/attempt_run_outcome_model", "policy_id", null],
  ["attempt_stage_event_ledger_v1", "/attempt_stage_event_ledger", "ledger_id", null],
  ["attempt_state_coherence_validator_v1", "/attempt_state_coherence_validator", "validator_id", null],
  ["attempt_state_compatibility_matrix_v1", "/attempt_state_compatibility_matrix", "matrix_id", "version"],
  ["canonical_parser_policy_json_v1", "/specification_identity/bootstrap_canonicalization", "policy_id", "version"],
  ["canonical_semantic_json_v1", "/semantic_canonicalization", "policy_id", null],
  ["citation_mapping_policy_v1", "/citation_mapping_policy", "policy_id", null],
  ["evidence_content_policy_v1", "/evidence_content_policy", "policy_id", null],
  ["evidence_id_policy_v1", "/evidence_id_policy", "policy_id", null],
  ["evidence_trace_coherence_validator_v1", "/evidence_type_coherence", "validator_id", null],
  ["failure_taxonomy_v1", "/failure_taxonomy", "policy_id", null],
  ["first_terminal_condition_reducer_v1", "/first_terminal_condition_reducer", "reducer_id", "version"],
  ["format_assertion_policy_v1", "/format_assertion_policy", "policy_id", null],
  ["native_structured_object_policy_v1", "/native_structured_object_policy", "policy_id", null],
  ["normalization_action_log_v1", "/normalization_action_log", "policy_id", null],
  ["normalization_action_vocabulary_v1", "/normalization_action_vocabulary", "policy_id", null],
  ["normalization_hashing_policy_v1", "/hashing_policy", "policy_id", null],
  ["normalization_parser_resource_limits_v1", "/resource_limit_policy", "policy_id", null],
  ["normalization_parser_security_v1", "/security_policy", "policy_id", null],
  ["normalization_result_record_requirements_v1", "/result_record_integration", "policy_id", null],
  ["normalization_status_model_v1", "/normalization_status_model", "policy_id", null],
  ["normalized_presemantic_state_v1", "/normalized_presemantic_state", "interface_id", null],
  ["objective_support_validator_v1", "/objective_support_validator", "validator_id", null],
  ["provider_role_mapping_contract_v1", "/provider_role_mapping_contract_v1", "policy_id", "policy_version"],
  ["raw_provider_response_policy_v1", "/raw_response_policy", "policy_id", null],
  ["refusal_policy_v1", "/refusal_policy", "policy_id", null],
  ["refusal_state_model_v1", "/refusal_state_model", "policy_id", null],
  ["research_objective_manifest_interface_v1", "/research_objective_manifest_interface", "interface_id", null],
  ["restricted_url_visibility_and_hash_policy_v1", "/restricted_url_visibility_and_hash_policy", "policy_id", null],
  ["retrieval_objective_support_policy_v1", "/retrieval_objective_support_policy_interface", "policy_id", null],
  ["retrieval_status_coherence_validator_v1", "/retrieval_status_coherence", "validator_id", null],
  ["retrieval_trace_ordering_policy_v1", "/retrieval_trace_ordering_policy", "policy_id", null],
  ["retrieval_validation_stage_model_v1", "/retrieval_validation_stage_model", "policy_id", null],
  ["retrieved_at_policy_v1", "/retrieved_at_policy", "policy_id", null],
  ["semantic_numeric_domain_policy_v1", "/semantic_numeric_domain_policy", "policy_id", "version"],
  ["semantic_repair_prohibition_v1", "/semantic_repair_policy", "policy_id", null],
  ["source_deduplication_policy_v1", "/source_deduplication_policy", "policy_id", null],
  ["source_display_name_policy_v1", "/source_display_name_policy", "policy_id", null],
  ["source_id_policy_v1", "/source_id_policy", "policy_id", null],
  ["strict_json_policy_v1", "/strict_json_policy", "policy_id", null],
  ["tool_failure_disposition_interface_v1", "/tool_failure_disposition_interface", "interface_id", null],
  ["transport_extraction_policy_v1", "/transport_extraction_policy", "policy_id", null],
  ["transport_topology_preflight_v1", "/transport_topology_preflight", "policy_id", null],
  ["url_policy_v1", "/url_policy", "policy_id", null],
  ["url_security_failure_policy_v1", "/url_security_failure_policy", "policy_id", null],
  ["url_security_policy_v1", "/url_security_policy_interface", "policy_id", null],
  ["url_security_validation_result_v1", "/url_security_validation_result", "policy_id", null],
  ["validator_state_model_v1", "/validator_state_model", "policy_id", null],
  ["workload_validator_applicability_v1", "/workload_validator_applicability", "policy_id", "version"],
];

const CHILD_EXCLUSIONS = Object.freeze({
  attempt_state_compatibility_matrix_v1: ["/hash_status"],
  semantic_numeric_domain_policy_v1: [
    "/numeric_policy_execution_conformance_status",
    "/policy_hash_status",
  ],
  workload_validator_applicability_v1: ["/hash_status"],
});

class ContractError extends Error {
  constructor(code) {
    super(code);
    this.name = "ContractError";
    this.code = code;
  }
}

function own(value, key) {
  return Object.prototype.hasOwnProperty.call(value, key);
}

class StrictParser {
  constructor(text) {
    this.text = text;
    this.index = 0;
  }

  parse() {
    this.skipWhitespace();
    const value = this.value();
    this.skipWhitespace();
    if (this.index !== this.text.length) this.fail("trailing_content");
    if (!isObject(value)) this.fail("root_not_object");
    return value;
  }

  fail(detail) {
    throw new ContractError(`strict_json:${detail}:${this.index}`);
  }

  skipWhitespace() {
    while (this.index < this.text.length) {
      const code = this.text.charCodeAt(this.index);
      if (code !== 0x20 && code !== 0x09 && code !== 0x0a && code !== 0x0d) break;
      this.index += 1;
    }
  }

  value() {
    const character = this.text[this.index];
    if (character === "{") return this.object();
    if (character === "[") return this.array();
    if (character === '"') return this.string();
    if (character === "t") return this.literal("true", true);
    if (character === "f") return this.literal("false", false);
    if (character === "n") return this.literal("null", null);
    if (character === "-" || (character >= "0" && character <= "9")) {
      return this.integer();
    }
    this.fail("value");
  }

  literal(token, value) {
    if (this.text.slice(this.index, this.index + token.length) !== token) {
      this.fail("literal");
    }
    this.index += token.length;
    return value;
  }

  object() {
    const result = Object.create(null);
    this.index += 1;
    this.skipWhitespace();
    if (this.text[this.index] === "}") {
      this.index += 1;
      return result;
    }
    while (true) {
      if (this.text[this.index] !== '"') this.fail("object_key");
      const key = this.string();
      if (own(result, key)) this.fail("duplicate_key");
      this.skipWhitespace();
      if (this.text[this.index] !== ":") this.fail("colon");
      this.index += 1;
      this.skipWhitespace();
      result[key] = this.value();
      this.skipWhitespace();
      if (this.text[this.index] === "}") {
        this.index += 1;
        return result;
      }
      if (this.text[this.index] !== ",") this.fail("object_separator");
      this.index += 1;
      this.skipWhitespace();
    }
  }

  array() {
    const result = [];
    this.index += 1;
    this.skipWhitespace();
    if (this.text[this.index] === "]") {
      this.index += 1;
      return result;
    }
    while (true) {
      result.push(this.value());
      this.skipWhitespace();
      if (this.text[this.index] === "]") {
        this.index += 1;
        return result;
      }
      if (this.text[this.index] !== ",") this.fail("array_separator");
      this.index += 1;
      this.skipWhitespace();
    }
  }

  string() {
    let result = "";
    this.index += 1;
    while (this.index < this.text.length) {
      const code = this.text.charCodeAt(this.index);
      if (code === 0x22) {
        this.index += 1;
        return result;
      }
      if (code === 0x5c) {
        this.index += 1;
        result += this.escape();
        continue;
      }
      if (code < 0x20) this.fail("unescaped_control");
      if (code >= 0xd800 && code <= 0xdbff) {
        const low = this.text.charCodeAt(this.index + 1);
        if (!(low >= 0xdc00 && low <= 0xdfff)) this.fail("unpaired_surrogate");
        result += this.text.slice(this.index, this.index + 2);
        this.index += 2;
        continue;
      }
      if (code >= 0xdc00 && code <= 0xdfff) this.fail("unpaired_surrogate");
      result += this.text[this.index];
      this.index += 1;
    }
    this.fail("unterminated_string");
  }

  escape() {
    const character = this.text[this.index];
    this.index += 1;
    const simple = {
      '"': '"',
      "\\": "\\",
      "/": "/",
      b: "\b",
      f: "\f",
      n: "\n",
      r: "\r",
      t: "\t",
    };
    if (own(simple, character)) return simple[character];
    if (character !== "u") this.fail("escape");
    const high = this.hexUnit();
    if (high >= 0xd800 && high <= 0xdbff) {
      if (this.text.slice(this.index, this.index + 2) !== "\\u") {
        this.fail("unpaired_surrogate");
      }
      this.index += 2;
      const low = this.hexUnit();
      if (!(low >= 0xdc00 && low <= 0xdfff)) this.fail("unpaired_surrogate");
      return String.fromCodePoint(0x10000 + ((high - 0xd800) << 10) + low - 0xdc00);
    }
    if (high >= 0xdc00 && high <= 0xdfff) this.fail("unpaired_surrogate");
    return String.fromCodePoint(high);
  }

  hexUnit() {
    const token = this.text.slice(this.index, this.index + 4);
    if (!/^[0-9a-fA-F]{4}$/u.test(token)) this.fail("unicode_escape");
    this.index += 4;
    return Number.parseInt(token, 16);
  }

  integer() {
    const start = this.index;
    if (this.text[this.index] === "-") this.index += 1;
    if (this.text[this.index] === "0") {
      this.index += 1;
      if (this.text[this.index] >= "0" && this.text[this.index] <= "9") {
        this.fail("leading_zero");
      }
    } else {
      if (!(this.text[this.index] >= "1" && this.text[this.index] <= "9")) {
        this.fail("integer");
      }
      while (this.text[this.index] >= "0" && this.text[this.index] <= "9") {
        this.index += 1;
      }
    }
    const token = this.text.slice(start, this.index);
    if (token === "-0") this.fail("negative_zero");
    const next = this.text[this.index];
    if (next === "." || next === "e" || next === "E") this.fail("noninteger");
    const value = BigInt(token);
    if (value < -SAFE_INTEGER || value > SAFE_INTEGER) this.fail("integer_domain");
    return Number(value);
  }
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function parseStrict(bytes) {
  if (bytes.length >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
    throw new ContractError("strict_json:bom");
  }
  let text;
  try {
    text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes);
  } catch {
    throw new ContractError("strict_json:utf8");
  }
  return new StrictParser(text).parse();
}

function compareScalars(left, right) {
  const a = Array.from(left, (character) => character.codePointAt(0));
  const b = Array.from(right, (character) => character.codePointAt(0));
  for (let index = 0; index < Math.min(a.length, b.length); index += 1) {
    if (a[index] !== b[index]) return a[index] - b[index];
  }
  return a.length - b.length;
}

function canonicalString(value) {
  let result = '"';
  for (const character of value) {
    const code = character.codePointAt(0);
    if (character === '"') result += '\\"';
    else if (character === "\\") result += "\\\\";
    else if (code === 0x08) result += "\\b";
    else if (code === 0x09) result += "\\t";
    else if (code === 0x0a) result += "\\n";
    else if (code === 0x0c) result += "\\f";
    else if (code === 0x0d) result += "\\r";
    else if (code <= 0x1f) result += `\\u00${code.toString(16).padStart(2, "0")}`;
    else result += character;
  }
  return `${result}"`;
}

function canonical(value) {
  if (value === null) return "null";
  if (value === true) return "true";
  if (value === false) return "false";
  if (typeof value === "number" && Number.isSafeInteger(value)) return String(value);
  if (typeof value === "string") return canonicalString(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (isObject(value)) {
    return `{${Object.keys(value)
      .sort(compareScalars)
      .map((key) => `${canonicalString(key)}:${canonical(value[key])}`)
      .join(",")}}`;
  }
  throw new ContractError("canonical_json:type");
}

function canonicalBytes(value) {
  return Buffer.from(canonical(value), "utf8");
}

function validateCanonicalBootstrap() {
  const orderingVector = object([
    ["😀", 1],
    ["", 2],
    ["aa", 3],
    ["a", 4],
    ["A", 5],
  ]);
  if (canonical(orderingVector) !== '{"A":5,"a":4,"aa":3,"":2,"😀":1}') {
    throw new ContractError("canonical_json:scalar_order");
  }
  const escapingVector = '"\\/\b\t\n\f\r\u0000\u001f  😀';
  if (canonical(escapingVector) !== '"\\"\\\\/\\b\\t\\n\\f\\r\\u0000\\u001f  😀"') {
    throw new ContractError("canonical_json:string_escaping");
  }
}

function validatePointerBootstrap() {
  const vector = object([
    ["a/b", 1],
    ["m~n", 2],
    ["arr", [object([["x", 3]]), 4]],
  ]);
  if (resolvePointer(vector, "") !== vector ||
      resolvePointer(vector, "/a~1b") !== 1 ||
      resolvePointer(vector, "/m~0n") !== 2 ||
      resolvePointer(vector, "/arr/0/x") !== 3) {
    throw new ContractError("json_pointer:self_test");
  }
  const invalid = [
    ["/m~2n", "json_pointer:escape"],
    ["/arr/00", "json_pointer:index"],
    ["/arr/-", "json_pointer:index"],
    ["/arr/2", "json_pointer:missing"],
    ["/arr/9007199254740992", "json_pointer:index"],
    ["/arr/0/x/y", "json_pointer:missing"],
  ];
  for (const [pointer, expected] of invalid) {
    try {
      resolvePointer(vector, pointer);
      throw new ContractError("json_pointer:self_test_acceptance");
    } catch (error) {
      if (!(error instanceof ContractError) || error.code !== expected) {
        throw new ContractError("json_pointer:self_test_error_class");
      }
    }
  }
  try {
    filteredCopy(vector, ["/a~1b", "/a~1b"]);
    throw new ContractError("json_pointer:self_test_duplicate");
  } catch (error) {
    if (!(error instanceof ContractError) || error.code !== "exclusions:duplicate_or_type") {
      throw new ContractError("json_pointer:self_test_duplicate_class");
    }
  }
  try {
    deletePointer(deepClone(vector), "");
    throw new ContractError("json_pointer:self_test_root_deletion");
  } catch (error) {
    if (!(error instanceof ContractError) ||
        error.code !== "json_pointer:root_deletion_forbidden") {
      throw new ContractError("json_pointer:self_test_root_deletion_class");
    }
  }
  const arrayVector = object([["arr", [0, 1, 2]]]);
  const filtered = filteredCopy(arrayVector, ["/arr/0", "/arr/1"]);
  if (canonical(filtered) !== '{"arr":[2]}') {
    throw new ContractError("json_pointer:self_test_array_deletion");
  }
}

function object(entries) {
  const result = Object.create(null);
  for (const [key, value] of entries) result[key] = value;
  return result;
}

function deepClone(value) {
  if (Array.isArray(value)) return value.map(deepClone);
  if (isObject(value)) {
    return object(Object.keys(value).map((key) => [key, deepClone(value[key])]));
  }
  return value;
}

function pointerSegments(pointer) {
  if (pointer === "") return [];
  if (typeof pointer !== "string" || !pointer.startsWith("/")) {
    throw new ContractError("json_pointer:invalid");
  }
  return pointer.slice(1).split("/").map((encoded) => {
    let result = "";
    for (let index = 0; index < encoded.length; index += 1) {
      if (encoded[index] !== "~") {
        result += encoded[index];
        continue;
      }
      const escape = encoded[index + 1];
      if (escape !== "0" && escape !== "1") throw new ContractError("json_pointer:escape");
      result += escape === "0" ? "~" : "/";
      index += 1;
    }
    return result;
  });
}

function arrayIndex(segment) {
  if (!/^(0|[1-9][0-9]*)$/u.test(segment)) throw new ContractError("json_pointer:index");
  const index = Number(segment);
  if (!Number.isSafeInteger(index)) throw new ContractError("json_pointer:index");
  return index;
}

function resolvePointer(document, pointer) {
  let current = document;
  for (const segment of pointerSegments(pointer)) {
    if (Array.isArray(current)) {
      const index = arrayIndex(segment);
      if (index >= current.length) throw new ContractError("json_pointer:missing");
      current = current[index];
    } else if (isObject(current) && own(current, segment)) {
      current = current[segment];
    } else {
      throw new ContractError("json_pointer:missing");
    }
  }
  return current;
}

function deletePointer(document, pointer) {
  const segments = pointerSegments(pointer);
  if (segments.length === 0) throw new ContractError("json_pointer:root_deletion_forbidden");
  const final = segments.pop();
  let parent = document;
  for (const segment of segments) {
    if (Array.isArray(parent)) parent = parent[arrayIndex(segment)];
    else parent = parent[segment];
  }
  if (Array.isArray(parent)) parent.splice(arrayIndex(final), 1);
  else delete parent[final];
}

function filteredCopy(document, pointers) {
  if (!Array.isArray(pointers) || new Set(pointers).size !== pointers.length) {
    throw new ContractError("exclusions:duplicate_or_type");
  }
  for (const pointer of pointers) resolvePointer(document, pointer);
  const result = deepClone(document);
  const ordered = [...pointers].sort((left, right) => {
    const leftSegments = pointerSegments(left);
    const rightSegments = pointerSegments(right);
    if (leftSegments.length !== rightSegments.length) {
      return rightSegments.length - leftSegments.length;
    }
    const leftParentPointer = `/${leftSegments.slice(0, -1)
      .map((segment) => segment.replaceAll("~", "~0").replaceAll("/", "~1"))
      .join("/")}`;
    const rightParentPointer = `/${rightSegments.slice(0, -1)
      .map((segment) => segment.replaceAll("~", "~0").replaceAll("/", "~1"))
      .join("/")}`;
    if (leftParentPointer === rightParentPointer) {
      const parent = leftSegments.length === 1
        ? document
        : resolvePointer(document, leftParentPointer);
      if (Array.isArray(parent)) {
        return arrayIndex(rightSegments.at(-1)) - arrayIndex(leftSegments.at(-1));
      }
    }
    return compareScalars(left, right);
  });
  for (const pointer of ordered) deletePointer(result, pointer);
  return result;
}

function sameSet(left, right) {
  return left.length === right.length &&
    new Set(left).size === left.length &&
    new Set(right).size === right.length &&
    left.every((value) => right.includes(value));
}

function exactKeys(value, expected, label) {
  if (!isObject(value) || !sameSet(Object.keys(value), expected)) {
    throw new ContractError(`${label}:shape`);
  }
}

function scalarLeaf(value) {
  return value === null || typeof value === "string" || typeof value === "number" || typeof value === "boolean";
}

function validateHash(value, label) {
  if (typeof value !== "string" || !SHA256.test(value)) {
    throw new ContractError(`${label}:hash_format`);
  }
  return value;
}

function expectedSpecExclusions(ids) {
  const lifecycle = [
    "/status",
    "/execution_boundary/implementation_status",
    "/semantic_numeric_domain_policy/numeric_policy_execution_conformance_status",
    "/semantic_numeric_domain_policy/policy_hash_status",
    "/workload_validator_applicability/hash_status",
    "/attempt_state_compatibility_matrix/hash_status",
    ...Array.from({ length: 8 }, (_, index) => `/p1_resolution_status/P1 #${index + 1}`),
  ];
  return [
    ...lifecycle,
    "/provider_calls_completed",
    "/specification_identity/derived_hash_cache/normalization_spec_semantic_hash",
    ...ids.map((id) => `/specification_identity/derived_hash_cache/registered_policy_semantic_hashes/${id}`),
    ...ids.map((id) => `/specification_identity/embedded_policy_registry/${id}/expected_semantic_hash`),
  ];
}

function validateExclusions(artifact, identity, ids) {
  const declared = identity.specification_semantic_excluded_json_pointers;
  const expected = expectedSpecExclusions(ids);
  if (!Array.isArray(declared) || declared.length !== 114 || !sameSet(declared, expected)) {
    throw new ContractError("exclusions:closed_inventory");
  }
  for (const pointer of declared) {
    if (!scalarLeaf(resolvePointer(artifact, pointer))) {
      throw new ContractError("exclusions:target_not_scalar");
    }
  }

  const rules = identity.specification_exclusion_rules;
  exactKeys(rules, [
    "list_is_closed",
    "wildcards_allowed",
    "key_name_patterns_allowed",
    "prefix_based_exclusions_allowed",
    "recursive_exclusions_allowed",
    "runtime_selected_exclusions_allowed",
    "missing_pointer_result",
    "duplicate_pointer_result",
    "unclassified_pointer_result",
    "descendants_inherit_ancestor_exclusion",
    "open_parent_object_exclusion_allowed",
    "allowed_exclusion_target_kinds",
    "every_excluded_value_requires_classification",
    "exclusion_classification",
    "classification_pointer_set_must_equal_exclusion_pointer_set",
    "p1_resolution_status_shape",
    "derived_hash_cache_shape",
    "exclusion_validation_order",
    "validation_failure_result",
    "provider_attempt_created_on_validation_failure",
    "restrictive_execution_authority_rules_are_excluded",
    "pending_dependency_requirements_are_excluded",
    "external_frozen_hash_bindings_are_excluded",
    "normative_prose_is_excluded",
  ], "exclusion_rules");
  if (rules.list_is_closed !== true || rules.wildcards_allowed !== false ||
      rules.key_name_patterns_allowed !== false ||
      rules.prefix_based_exclusions_allowed !== false ||
      rules.recursive_exclusions_allowed !== false ||
      rules.runtime_selected_exclusions_allowed !== false ||
      rules.descendants_inherit_ancestor_exclusion !== false ||
      rules.open_parent_object_exclusion_allowed !== false ||
      rules.every_excluded_value_requires_classification !== true ||
      rules.provider_attempt_created_on_validation_failure !== false ||
      rules.restrictive_execution_authority_rules_are_excluded !== false ||
      rules.pending_dependency_requirements_are_excluded !== false ||
      rules.external_frozen_hash_bindings_are_excluded !== false ||
      rules.normative_prose_is_excluded !== false) {
    throw new ContractError("exclusions:governance_flags");
  }
  if (!sameSet(rules.allowed_exclusion_target_kinds, [
    "exact scalar or leaf derived value",
    "complete object with a separately frozen, machine-validated, exclusively non-semantic closed shape",
  ])) {
    throw new ContractError("exclusions:target_kinds");
  }
  const classes = rules.exclusion_classification;
  exactKeys(classes, [
    "lifecycle_reporting_only_exact_pointers",
    "runtime_counter_exact_pointers",
    "registry_expected_hash_values",
    "central_specification_hash_value_exact_pointers",
    "central_registered_policy_hash_values",
  ], "exclusion_classes");
  const lifecycle = expected.slice(0, 14);
  if (!sameSet(classes.lifecycle_reporting_only_exact_pointers, lifecycle)) {
    throw new ContractError("exclusions:lifecycle_classification");
  }
  if (!sameSet(classes.runtime_counter_exact_pointers, ["/provider_calls_completed"])) {
    throw new ContractError("exclusions:counter_classification");
  }
  if (!sameSet(classes.central_specification_hash_value_exact_pointers, [
    "/specification_identity/derived_hash_cache/normalization_spec_semantic_hash",
  ])) {
    throw new ContractError("exclusions:spec_hash_classification");
  }
  for (const [label, declaration] of [
    ["registry", classes.registry_expected_hash_values],
    ["central", classes.central_registered_policy_hash_values],
  ]) {
    exactKeys(declaration, ["classification", "pointer_set", "key_set_equality_required"], `exclusion_${label}`);
    if (declaration.classification !== "mechanically recomputed derived hash leaves" ||
        declaration.key_set_equality_required !== true ||
        typeof declaration.pointer_set !== "string") {
      throw new ContractError(`exclusions:${label}_classification`);
    }
  }
  if (rules.classification_pointer_set_must_equal_exclusion_pointer_set !== true) {
    throw new ContractError("exclusions:classification_not_closed");
  }
  const p1 = rules.p1_resolution_status_shape;
  exactKeys(p1, [
    "whole_object_excluded",
    "exact_reporting_leaf_keys",
    "additional_members_inherit_exclusion",
    "additional_member_participates_in_semantic_identity",
    "stale_expected_binding_result",
  ], "p1_exclusion_shape");
  const p1Keys = Array.from({ length: 8 }, (_, index) => `P1 #${index + 1}`);
  if (p1.whole_object_excluded !== false || p1.additional_members_inherit_exclusion !== false ||
      p1.additional_member_participates_in_semantic_identity !== true ||
      !sameSet(p1.exact_reporting_leaf_keys, p1Keys)) {
    throw new ContractError("exclusions:p1_shape");
  }
  const cacheShape = rules.derived_hash_cache_shape;
  exactKeys(cacheShape, [
    "whole_object_excluded",
    "allowed_top_level_keys",
    "semantic_governance_keys",
    "derived_hash_value_keys",
    "authoritative_value_type",
    "unexpected_or_missing_top_level_key_result",
    "arbitrary_metadata_extension_allowed",
    "registered_policy_semantic_hashes_shape",
  ], "cache_shape_declaration");
  if (cacheShape.whole_object_excluded !== false ||
      !sameSet(cacheShape.allowed_top_level_keys, [
        "authoritative",
        "normalization_spec_semantic_hash",
        "registered_policy_semantic_hashes",
      ]) ||
      !sameSet(cacheShape.semantic_governance_keys, ["authoritative"]) ||
      !sameSet(cacheShape.derived_hash_value_keys, [
        "normalization_spec_semantic_hash",
        "registered_policy_semantic_hashes",
      ]) ||
      cacheShape.authoritative_value_type !== "Boolean" ||
      cacheShape.arbitrary_metadata_extension_allowed !== false) {
    throw new ContractError("exclusions:cache_shape_declaration");
  }
  const registeredShape = cacheShape.registered_policy_semantic_hashes_shape;
  exactKeys(registeredShape, [
    "allowed_keys",
    "key_set_equality_required",
    "value_format",
    "unexpected_or_missing_key_result",
  ], "registered_cache_shape_declaration");
  if (registeredShape.allowed_keys !== "exactly the embedded_policy_registry keys" ||
      registeredShape.key_set_equality_required !== true ||
      registeredShape.value_format !== "exactly 64 lowercase hexadecimal characters") {
    throw new ContractError("exclusions:registered_cache_shape_declaration");
  }
}

function validateChildExclusions(identity) {
  const declared = identity.child_policy_exact_exclusions;
  exactKeys(declared, Object.keys(CHILD_EXCLUSIONS), "child_exclusions");
  for (const [id, expected] of Object.entries(CHILD_EXCLUSIONS)) {
    if (!Array.isArray(declared[id]) || !sameSet(declared[id], expected)) {
      throw new ContractError("child_exclusions:inventory");
    }
  }
}

function analyzeIdentity(bytes, includeCanonical) {
  validateCanonicalBootstrap();
  validatePointerBootstrap();
  const artifact = parseStrict(bytes);
  if (BINDINGS.length !== 49) throw new ContractError("reference:binding_count");
  const bindingIds = BINDINGS.map(([id]) => id);
  if (new Set(bindingIds).size !== 49) throw new ContractError("reference:binding_duplicate");

  const identity = artifact.specification_identity;
  if (!isObject(identity)) throw new ContractError("identity:shape");
  const registry = identity.embedded_policy_registry;
  exactKeys(registry, bindingIds, "registry");
  validateChildExclusions(identity);
  validateExclusions(artifact, identity, bindingIds);

  const cache = identity.derived_hash_cache;
  exactKeys(cache, ["authoritative", "normalization_spec_semantic_hash", "registered_policy_semantic_hashes"], "cache");
  if (typeof cache.authoritative !== "boolean") throw new ContractError("cache:authoritative_type");
  exactKeys(cache.registered_policy_semantic_hashes, bindingIds, "child_cache");

  const pointerSet = new Set();
  const pairSet = new Set();
  const childHashes = Object.create(null);
  const childCanonical = Object.create(null);
  const entries = [];
  for (const [id, expectedPointer, idField, versionField] of BINDINGS) {
    const record = registry[id];
    exactKeys(record, ["policy_id", "policy_version", "json_pointer", "hash_scope", "expected_semantic_hash"], "registry_record");
    const pair = `${record.policy_id}\u0000${record.policy_version}`;
    if (pairSet.has(pair) || pointerSet.has(record.json_pointer)) {
      throw new ContractError("registry:identity_uniqueness");
    }
    pairSet.add(pair);
    pointerSet.add(record.json_pointer);

    const subtree = resolvePointer(artifact, record.json_pointer);
    if (!isObject(subtree)) throw new ContractError(`registry:subtree_type:${id}`);
    const excluded = own(CHILD_EXCLUSIONS, id) ? CHILD_EXCLUSIONS[id] : [];
    const content = filteredCopy(subtree, excluded);
    const envelope = object([
      ["identity_domain", "trustai.embedded_policy.v1"],
      ["policy_id", record.policy_id],
      ["policy_version", record.policy_version],
      ["content", content],
    ]);
    const canonicalChild = canonicalBytes(envelope);
    const computed = createHash("sha256").update(canonicalChild).digest("hex");
    childHashes[id] = computed;
    if (includeCanonical) childCanonical[id] = canonicalChild.toString("base64");
    entries.push({
      id,
      expectedPointer,
      idField,
      versionField,
      record,
      subtree,
      computed,
    });
  }

  const specContent = filteredCopy(
    artifact,
    identity.specification_semantic_excluded_json_pointers,
  );
  const specEnvelope = object([
    ["identity_domain", "trustai.normalization_spec.v1"],
    ["normalization_spec_id", identity.normalization_spec_id],
    ["normalization_spec_version", identity.normalization_spec_version],
    ["content", specContent],
  ]);
  const canonicalSpec = canonicalBytes(specEnvelope);
  const computedSpec = createHash("sha256").update(canonicalSpec).digest("hex");
  const result = {
    implementation_id: "normalization_spec_identity_javascript_reference_v1",
    normalization_spec_file_sha256: createHash("sha256").update(bytes).digest("hex"),
    normalization_spec_semantic_hash: computedSpec,
    child_hashes: childHashes,
    canonical_bootstrap_self_test: true,
    pointer_bootstrap_self_test: true,
    provider_calls_required: false,
  };
  if (includeCanonical) {
    result.normalization_spec_canonical_base64 = canonicalSpec.toString("base64");
    result.child_canonical_base64 = childCanonical;
  }
  return {
    artifact,
    identity,
    registry,
    cache,
    entries,
    result,
  };
}

function verifyFrozenIdentity(analysis, authorizedSpecHash, promptHash, schemaHash) {
  const { artifact, identity, cache, entries, result } = analysis;
  validateHash(authorizedSpecHash, "authorized_spec");
  for (const entry of entries) {
    const { id, expectedPointer, idField, versionField, record, subtree, computed } = entry;
    if (record.policy_id !== id) throw new ContractError(`registry:policy_id_binding:${id}`);
    if (record.policy_version !== "v1") {
      throw new ContractError(`registry:expected_binding:${id}`);
    }
    if (record.json_pointer !== expectedPointer) {
      throw new ContractError(`registry:spec_binding:${id}`);
    }
    if (record.hash_scope !== "complete_selected_subtree") {
      throw new ContractError(`registry:hash_scope:${id}`);
    }
    if (subtree[idField] !== record.policy_id) {
      throw new ContractError(`registry:subtree_identity:${id}`);
    }
    if (versionField !== null && subtree[versionField] !== record.policy_version) {
      throw new ContractError(`registry:subtree_version:${id}`);
    }
    if (versionField === null && (own(subtree, "version") || own(subtree, "policy_version"))) {
      throw new ContractError(`registry:unexpected_subtree_version:${id}`);
    }
    if (computed !== validateHash(record.expected_semantic_hash, "registry_expected")) {
      throw new ContractError(`child_hash:registry:${id}`);
    }
    if (computed !== validateHash(cache.registered_policy_semantic_hashes[id], "child_cache")) {
      throw new ContractError(`child_hash:cache:${id}`);
    }
  }
  const cachedSpec = validateHash(cache.normalization_spec_semantic_hash, "spec_cache");
  if (result.normalization_spec_semantic_hash !== cachedSpec ||
      result.normalization_spec_semantic_hash !== authorizedSpecHash) {
    throw new ContractError("spec_hash:stale_binding");
  }
  if (cache.authoritative !== false) throw new ContractError("cache:authoritative_must_be_false");
  if (promptHash !== EXPECTED_PROMPT_HASH || schemaHash !== EXPECTED_SCHEMA_HASH) {
    throw new ContractError("external_binding:argument");
  }
  const external = identity.external_dependency_hashes;
  if (external.prompt_template_set_hash_expected !== promptHash ||
      external.output_schema_set_hash_expected !== schemaHash ||
      artifact.frozen_references.prompt_template_set_hash !== promptHash ||
      artifact.frozen_references.output_schema_set_hash !== schemaHash) {
    throw new ContractError("external_binding:artifact");
  }
  return result;
}

function main() {
  const [path, authorizedSpecHash, promptHash, schemaHash, ...flags] = process.argv.slice(2);
  if (!path || !authorizedSpecHash || !promptHash || !schemaHash) {
    throw new ContractError("cli:arguments");
  }
  const unknown = flags.filter((flag) =>
    flag !== "--include-canonical" && flag !== "--analyze" && flag !== "--parse-only"
  );
  if (unknown.length !== 0) throw new ContractError("cli:flag");
  const bytes = readFileSync(path);
  if (flags.includes("--parse-only")) {
    parseStrict(bytes);
    return {
      valid: true,
      strict_parse_valid: true,
      provider_calls_required: false,
    };
  }
  const analysis = analyzeIdentity(bytes, flags.includes("--include-canonical"));
  if (flags.includes("--analyze")) {
    try {
      verifyFrozenIdentity(analysis, authorizedSpecHash, promptHash, schemaHash);
      return { valid: true, preflight_valid: true, ...analysis.result };
    } catch (error) {
      if (!(error instanceof ContractError)) throw error;
      return {
        valid: false,
        preflight_valid: false,
        error: error.code,
        ...analysis.result,
      };
    }
  }
  return {
    valid: true,
    ...verifyFrozenIdentity(analysis, authorizedSpecHash, promptHash, schemaHash),
  };
}

try {
  process.stdout.write(`${JSON.stringify(main())}\n`);
} catch (error) {
  const code = error instanceof ContractError ? error.code : "internal_error";
  process.stdout.write(`${JSON.stringify({ valid: false, error: code, provider_calls_required: false })}\n`);
  process.stderr.write(`${code}\n`);
  process.exitCode = 1;
}
