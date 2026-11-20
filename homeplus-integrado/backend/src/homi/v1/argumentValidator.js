'use strict';

/**
 * HomePlus Homi Tool Layer — runtime argument validation (T07-S4).
 *
 * Pure module. It validates the runtime arguments of a tool invocation
 * against the input schema declared by its Tool Definition. It performs no
 * I/O, holds no client and depends on no business service.
 *
 * The validator implements exactly the schema subset that the production
 * READ tool definitions of this slice use:
 *
 *   type (string | integer | boolean | number)
 *   enum
 *   required
 *   additionalProperties: false
 *   minLength / maxLength
 *   minimum / maximum
 *   pattern
 *
 * It is deliberately NOT a general JSON Schema implementation. Any keyword or
 * type combination outside the supported subset fails closed with
 * `HOMI_TOOL_ARGUMENT_INVALID` instead of being silently ignored.
 *
 * The validation is strict: no value is ever coerced. `limit: "10"` is a type
 * error, never the integer `10`.
 */

const HOMI_TOOL_ARGUMENT_INVALID = 'HOMI_TOOL_ARGUMENT_INVALID';

const SUPPORTED_TYPES = Object.freeze(['string', 'integer', 'boolean', 'number', 'array', 'object']);

const SUPPORTED_KEYWORDS = Object.freeze([
  'type',
  'enum',
  'description',
  'properties',
  'required',
  'additionalProperties',
  'minLength',
  'maxLength',
  'minimum',
  'maximum',
  'pattern',
  // arrays
  'items',
  'minItems',
  'maxItems',
]);

/**
 * Stable internal error type for a rejected tool argument.
 *
 * The details carry the offending field name and a machine readable reason
 * only. The offending VALUE is never copied into the error: it may carry
 * personal data and it must never reach a response or a log line.
 */
class HomiArgumentError extends Error {
  constructor(code, message, details) {
    super(message);
    this.name = 'HomiArgumentError';
    this.code = code;
    this.details = Object.freeze({ ...(details || {}) });
  }
}

const isPlainObject = (value) => {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
};

const hasOwn = (object, key) => Object.prototype.hasOwnProperty.call(object, key);

/**
 * @param {string} reason machine readable rejection reason
 * @param {object} [details] safe metadata (field name only)
 * @returns {HomiArgumentError} the error to throw
 */
function invalidArgument(reason, details) {
  const field = details && typeof details.field === 'string' ? details.field : null;

  return new HomiArgumentError(
    HOMI_TOOL_ARGUMENT_INVALID,
    field
      ? `The tool argument "${field}" is not valid (${reason}).`
      : `The tool arguments are not valid (${reason}).`,
    { reason, ...(field ? { field } : {}) }
  );
}

const patternCache = new Map();

/**
 * Compile (and cache) the regular expression of a schema pattern.
 *
 * @param {string} pattern source regular expression
 * @returns {RegExp} the compiled expression
 */
function compilePattern(pattern) {
  const cached = patternCache.get(pattern);
  if (cached) return cached;

  const compiled = new RegExp(pattern);
  patternCache.set(pattern, compiled);
  return compiled;
}

/**
 * Reject a schema that uses a construct outside the supported subset.
 *
 * @param {string} field argument name
 * @param {object} schema the declared property schema
 */
function assertSupportedSchema(field, schema) {
  if (!isPlainObject(schema)) {
    throw invalidArgument('unsupported_schema', { field });
  }

  for (const keyword of Object.keys(schema)) {
    if (!SUPPORTED_KEYWORDS.includes(keyword)) {
      throw invalidArgument('unsupported_schema', { field });
    }
  }

  if (typeof schema.type !== 'string' || !SUPPORTED_TYPES.includes(schema.type)) {
    throw invalidArgument('unsupported_schema', { field });
  }

  if (schema.enum !== undefined && !Array.isArray(schema.enum)) {
    throw invalidArgument('unsupported_schema', { field });
  }

  if (schema.pattern !== undefined && typeof schema.pattern !== 'string') {
    throw invalidArgument('unsupported_schema', { field });
  }

  for (const bound of ['minLength', 'maxLength', 'minimum', 'maximum']) {
    if (schema[bound] !== undefined && typeof schema[bound] !== 'number') {
      throw invalidArgument('unsupported_schema', { field });
    }
  }

  if (schema.type === 'array') {
    if (schema.items !== undefined && !isPlainObject(schema.items)) {
      throw invalidArgument('unsupported_schema', { field });
    }
    for (const bound of ['minItems', 'maxItems']) {
      if (schema[bound] !== undefined && typeof schema[bound] !== 'number') {
        throw invalidArgument('unsupported_schema', { field });
      }
    }
  }

  if (schema.type === 'object') {
    if (schema.properties !== undefined && !isPlainObject(schema.properties)) {
      throw invalidArgument('unsupported_schema', { field });
    }
    if (schema.required !== undefined && !Array.isArray(schema.required)) {
      throw invalidArgument('unsupported_schema', { field });
    }
    if (schema.additionalProperties !== undefined && typeof schema.additionalProperties !== 'boolean') {
      throw invalidArgument('unsupported_schema', { field });
    }
    if (schema.properties !== undefined) {
      for (const key of Object.keys(schema.properties)) {
        assertSupportedSchema(`${field}.${key}`, schema.properties[key]);
      }
    }
  }
}

/**
 * Validate a single declared property value.
 *
 * @param {string} field argument name
 * @param {object} schema the declared property schema
 * @param {unknown} value the runtime value
 * @returns {unknown} the accepted value
 */
function validateNestedSchema(field, schema, value) {
  // Estructural recursivo para arrays y objetos anidados (subset soportado).
  if (schema.type === 'array') {
    if (!Array.isArray(value)) {
      throw invalidArgument('invalid_type', { field });
    }
    if (schema.minItems !== undefined && value.length < schema.minItems) {
      throw invalidArgument('below_min_items', { field });
    }
    if (schema.maxItems !== undefined && value.length > schema.maxItems) {
      throw invalidArgument('above_max_items', { field });
    }
    if (schema.items !== undefined) {
      for (let index = 0; index < value.length; index += 1) {
        validateNestedSchema(`${field}[${index}]`, schema.items, value[index]);
      }
    }
    return;
  }

  if (schema.type === 'object') {
    if (!isPlainObject(value)) {
      throw invalidArgument('invalid_type', { field });
    }
    const props = isPlainObject(schema.properties) ? schema.properties : {};
    const required = Array.isArray(schema.required) ? schema.required : [];
    const additional = schema.additionalProperties !== false;
    for (const key of Object.keys(value)) {
      if (!hasOwn(props, key) && !additional) {
        throw invalidArgument('unknown_argument', { field: `${field}.${key}` });
      }
      if (hasOwn(props, key)) {
        validateNestedSchema(`${field}.${key}`, props[key], value[key]);
      }
    }
    for (const key of required) {
      if (!hasOwn(value, key)) {
        throw invalidArgument('missing_required_argument', { field: `${field}.${key}` });
      }
    }
    return;
  }
  // Tipos primitivos con restricciones de cadena/numero/enum.
  validatePropertyValue(field, schema, value);
}

function validatePropertyValue(field, schema, value) {
  assertSupportedSchema(field, schema);

  if (schema.type === 'string' && typeof value !== 'string') {
    throw invalidArgument('invalid_type', { field });
  }

  if (schema.type === 'boolean' && typeof value !== 'boolean') {
    throw invalidArgument('invalid_type', { field });
  }

  if (schema.type === 'integer') {
    if (typeof value !== 'number' || !Number.isInteger(value)) {
      throw invalidArgument('invalid_type', { field });
    }
  }

  if (schema.type === 'number') {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      throw invalidArgument('invalid_type', { field });
    }
  }

  if (schema.type === 'array' || schema.type === 'object') {
    validateNestedSchema(field, schema, value);
    return value;
  }

  if (schema.enum !== undefined && !schema.enum.includes(value)) {
    throw invalidArgument('invalid_enum', { field });
  }

  if (typeof value === 'string') {
    if (schema.minLength !== undefined && value.length < schema.minLength) {
      throw invalidArgument('too_short', { field });
    }

    if (schema.maxLength !== undefined && value.length > schema.maxLength) {
      throw invalidArgument('too_long', { field });
    }

    if (schema.pattern !== undefined && !compilePattern(schema.pattern).test(value)) {
      throw invalidArgument('pattern_mismatch', { field });
    }
  }

  if (typeof value === 'number') {
    if (schema.minimum !== undefined && value < schema.minimum) {
      throw invalidArgument('below_minimum', { field });
    }

    if (schema.maximum !== undefined && value > schema.maximum) {
      throw invalidArgument('above_maximum', { field });
    }
  }

  return value;
}

/**
 * Validate the runtime arguments of a tool invocation.
 *
 * @param {object} inputSchema the `inputSchema` of the tool definition
 * @param {unknown} args the runtime arguments
 * @returns {object} the accepted, frozen arguments
 * @throws {HomiArgumentError} HOMI_TOOL_ARGUMENT_INVALID
 */
function validateToolArguments(inputSchema, args) {
  if (!isPlainObject(inputSchema) || inputSchema.type !== 'object') {
    throw invalidArgument('unsupported_schema');
  }

  if (!isPlainObject(args)) {
    throw invalidArgument('args_not_an_object');
  }

  const properties = isPlainObject(inputSchema.properties) ? inputSchema.properties : {};
  const required = Array.isArray(inputSchema.required) ? inputSchema.required : [];

  const validated = {};

  for (const field of Object.keys(args)) {
    const value = args[field];

    // JSON carries no `undefined`: an explicit undefined is an absent
    // argument, never a value.
    if (value === undefined) continue;

    if (!hasOwn(properties, field)) {
      throw invalidArgument('unknown_argument', { field });
    }

    validated[field] = validatePropertyValue(field, properties[field], value);
  }

  for (const field of required) {
    if (!hasOwn(validated, field)) {
      throw invalidArgument('missing_required_argument', { field });
    }
  }

  return Object.freeze(validated);
}

module.exports = {
  HOMI_TOOL_ARGUMENT_INVALID,
  HomiArgumentError,
  SUPPORTED_TYPES,
  validateToolArguments,
};
