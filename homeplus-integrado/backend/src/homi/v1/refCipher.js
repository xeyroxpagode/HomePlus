'use strict';

/**
 * HomePlus Homi Tool Layer — opaque reference cipher (T24-I1).
 *
 * The nine multidomain READ tools never expose raw identifiers (memberships,
 * transactions, inventory items, restock requests) to the model. Every
 * reference is an opaque, authenticated token produced with AES-256-GCM
 * under a per-process random key.
 *
 * Properties:
 *   * stateless: decryption does not need a table or a lookup;
 *   * ephemeral: the key is random per process, so handles minted before a
 *     restart are not resolvable afterwards (acceptable for ephemeral,
 *     short-lived chat handles);
 *   * authenticated: tampering with a handle is detected and rejected;
 *   * scoped resolution: after decryption the resolved identifier is always
 *     re-checked against the authoritative household/context and RLS.
 *
 * This module uses only node:crypto. It holds no secret from the
 * environment and is never serialized.
 */

const crypto = require('crypto');

const ALGORITHM = 'aes-256-gcm';

// Random per-process key. Not shared, not persisted, not logged.
const KEY = crypto.randomBytes(32);

const IV_BYTES = 12;
const TAG_BYTES = 16;

/**
 * Encrypt an identifier into an opaque base64url handle.
 *
 * @param {string} id the raw identifier (validated non-empty string)
 * @returns {string} the opaque reference
 * @throws {TypeError} when the identifier is not a non-empty string
 */
function encryptRef(id) {
  if (typeof id !== 'string' || id.trim().length === 0) {
    throw new TypeError('encryptRef requires a non-empty string identifier.');
  }

  const iv = crypto.randomBytes(IV_BYTES);
  const cipher = crypto.createCipheriv(ALGORITHM, KEY, iv);
  const ciphertext = Buffer.concat([cipher.update(id, 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();

  return Buffer.concat([iv, tag, ciphertext]).toString('base64url');
}

/**
 * Decrypt an opaque reference back into the raw identifier.
 *
 * @param {unknown} ref the opaque handle from the caller
 * @returns {string|null} the identifier or null when the handle is invalid,
 *   malformed or fails authentication
 */
function decryptRef(ref) {
  if (typeof ref !== 'string' || ref.trim().length === 0) return null;

  try {
    const raw = Buffer.from(ref.trim(), 'base64url');

    if (raw.length < IV_BYTES + TAG_BYTES + 1) return null;

    const iv = raw.subarray(0, IV_BYTES);
    const tag = raw.subarray(IV_BYTES, IV_BYTES + TAG_BYTES);
    const ciphertext = raw.subarray(IV_BYTES + TAG_BYTES);

    const decipher = crypto.createDecipheriv(ALGORITHM, KEY, iv);
    decipher.setAuthTag(tag);

    return Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString('utf8');
  } catch {
    return null;
  }
}

module.exports = {
  encryptRef,
  decryptRef,
};
