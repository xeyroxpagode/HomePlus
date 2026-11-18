/* Server/CI maintenance only — never exposed as an HTTP endpoint.
 * Removes uncommitted private objects older than 24h, then their staging row.
 */
require('dotenv').config()
const { supabaseAdmin } = require('../src/config/supabase')

async function main() {
  if (!supabaseAdmin) throw new Error('SUPABASE_SERVICE_ROLE_KEY is required')
  const cutoff = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString()
  const { data, error } = await supabaseAdmin.from('messaging_attachments')
    .select('id, storage_bucket, storage_path').is('message_id', null).lt('created_at', cutoff).in('lifecycle', ['uploading', 'uploaded', 'failed']).limit(250)
  if (error) throw error
  for (const attachment of data ?? []) {
    await supabaseAdmin.storage.from(attachment.storage_bucket).remove([attachment.storage_path]).catch(() => {})
    const { error: deleteError } = await supabaseAdmin.from('messaging_attachments').delete().eq('id', attachment.id).is('message_id', null)
    if (deleteError) throw deleteError
  }
  console.log(`[messaging-attachments] cleaned ${data?.length ?? 0} expired staging attachments`)
}
main().catch(() => { console.error('[messaging-attachments] cleanup failed'); process.exitCode = 1 })
