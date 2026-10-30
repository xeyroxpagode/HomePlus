'use strict';

/**
 * Convert a backend-issued Supabase signed URL into its client-facing form.
 * Only the origin is configurable; the signed path and query remain untouched.
 */
function resolvePublicSignedUploadUrl(
  signedUrl,
  configuredPublicUrl = process.env.HOMECLOUD_PUBLIC_STORAGE_URL,
) {
  const rawPublicUrl = typeof configuredPublicUrl === 'string' ? configuredPublicUrl.trim() : '';
  if (!rawPublicUrl) return signedUrl;

  try {
    const signed = new URL(signedUrl);
    const publicUrl = new URL(rawPublicUrl);
    if (!['http:', 'https:'].includes(publicUrl.protocol)) return signedUrl;
    return `${publicUrl.origin}${signed.pathname}${signed.search}${signed.hash}`;
  } catch {
    return signedUrl;
  }
}

module.exports = { resolvePublicSignedUploadUrl };
