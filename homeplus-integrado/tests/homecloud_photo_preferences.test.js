const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function preferences({allowed=true,photo=true,album=true,member=true,missing=false}={}){
 const writes=[];const filters=[];
 const client={from(table){let operation=null;const q={select(){return q},eq(k,v){filters.push([table,k,v]);return q},upsert(value){operation=value;return q},delete(){operation='delete';return q},maybeSingle:async()=>({data:table==='homecloud_contents'?(photo?{id:'p',mime_type:'image/jpeg'}:null):table==='homecloud_albums'?(album?{id:'a'}:null):(member?{content_id:'p'}:null),error:null}),then(resolve){if(operation)writes.push([table,operation]);resolve({data:[],error:missing?{code:'PGRST205'}:null});}};return q;}};
 const module={exports:{}};vm.runInNewContext(fs.readFileSync('backend/src/services/homecloudPhotoPreferencesService.js','utf8'),{module,exports:module.exports,require:n=>n.includes('config/supabase')?{supabaseAdmin:client}:n.includes('context.service')?{getHomeCloudContext:async()=>({accountId:'account',householdId:'own',household:{},membership:{role:'coordinator',status:'active'}})}:n.includes('Capabilities')?{resolveHomeCloudCapabilities:()=>({}),assertHomeCloudCapability:()=>{if(!allowed)throw Object.assign(Error('denied'),{status:403})}}:{createHttpError:(status,message)=>Object.assign(Error(message),{status})}});
 const id='11111111-1111-4111-8111-111111111111';return {service:module.exports,req:{params:{albumId:id,contentId:id}},writes,filters};
}
test('favorites use server account identity and require a photo in the authorized household',async()=>{
 const h=preferences();await h.service.favorite(h.req,true);assert.equal(h.writes[0][1].account_id,'account');assert.ok(h.filters.some(([,k,v])=>k==='household_id'&&v==='own'));
 const denied=preferences({photo:false});await assert.rejects(denied.service.favorite(denied.req,true),e=>e.status===404);assert.equal(denied.writes.length,0);
});
test('cover requires organization authority, own active album and existing photo membership',async()=>{
 for(const options of [{allowed:false},{album:false},{member:false},{photo:false}]){const h=preferences(options);await assert.rejects(h.service.cover(h.req),e=>e.status===(options.allowed===false?403:404));assert.equal(h.writes.length,0);}
 const h=preferences();await h.service.cover(h.req);assert.equal(h.writes[0][0],'homecloud_album_covers');
});
test('missing optional schema is explicit, never a fake list of persisted favorites',async()=>{const h=preferences({missing:true});const result=await h.service.read(h.req);assert.equal(result.available,false);assert.equal(result.favoriteIds,undefined);});
test('preference migration adds private metadata only; cover membership removal never deletes media',()=>{const sql=fs.readFileSync('supabase/migrations/20261118000000_homecloud_photo_preferences_v1.sql','utf8');assert.match(sql,/references public\.homecloud_album_items\(album_id, content_id\) on delete cascade/);assert.match(sql,/enable row level security/g);assert.match(sql,/from anon, authenticated/);assert.doesNotMatch(sql,/delete from|update public\.homecloud_contents|drop table|supabase_migrations/i);});
