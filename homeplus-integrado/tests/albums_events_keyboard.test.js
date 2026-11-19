const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const uuid='11111111-1111-4111-8111-111111111111';
function harness({allowed=true,foreignAlbum=false,foreignPhoto=false}={}){
 const mutations=[];
 const client={from(table){let filters={},write=null;const q={select(){return q},eq(k,v){filters[k]=v;return q},insert(v){write=v;return q},update(v){write=v;return q},delete(){write='delete';return q},upsert(v){write=v;return q},maybeSingle:async()=>({data:table==='homecloud_albums'?(foreignAlbum?null:{id:uuid,name:'Test',lifecycle:'active'}):(foreignPhoto?null:{id:uuid}),error:null}),single:async()=>({data:write,error:null}),then(resolve){mutations.push({table,filters,write});resolve({data:null,error:null});}};return q;}};
 const module={exports:{}};
 vm.runInNewContext(fs.readFileSync('backend/src/services/homecloudAlbumsService.js','utf8'),{module,exports:module.exports,require:n=>n.includes('config/supabase')?{supabaseAdmin:client}:n.includes('context.service')?{getHomeCloudContext:async()=>({householdId:'own',household:{},membership:{id:'member',role:'coordinator',status:'active'}})}:n.includes('Capabilities')?{resolveHomeCloudCapabilities:()=>({}),assertHomeCloudCapability:()=>{if(!allowed)throw Object.assign(Error('forbidden'),{status:403});}}:n.includes('Mappers')?{mapAlbumRowToDto:x=>x}:{createHttpError:(status,message)=>Object.assign(Error(message),{status})}});
 return {service:module.exports,mutations,req:{params:{albumId:uuid,contentId:uuid},body:{id:uuid,name:'Test'}}};
}
test('album mutations reject missing organization authority and foreign album before writing',async()=>{
 for(const options of [{allowed:false},{foreignAlbum:true}]){const h=harness(options);await assert.rejects(h.service.membership(h.req),e=>e.status===(options.allowed===false?403:404));assert.equal(h.mutations.length,0);}
});
test('membership rejects foreign photo and only modifies the join table',async()=>{
 const denied=harness({foreignPhoto:true});await assert.rejects(denied.service.membership(denied.req),e=>e.status===404);assert.equal(denied.mutations.length,0);
 const h=harness();await h.service.membership(h.req);await h.service.membership(h.req,true);assert.ok(h.mutations.every(x=>x.table==='homecloud_album_items'));assert.equal(h.mutations[1].write,'delete');
});
test('album trash preserves contents and membership rows',async()=>{const h=harness();await h.service.trash(h.req);assert.equal(h.mutations.length,1);assert.equal(h.mutations[0].table,'homecloud_albums');assert.equal(h.mutations[0].filters.household_id,'own');assert.equal(h.mutations[0].write.lifecycle,'trashed');});
test('album retry with same intent returns the same album without a second insert',async()=>{const h=harness();assert.equal((await h.service.create(h.req)).id,uuid);assert.equal(h.mutations.length,0);h.req.body.name='Different';await assert.rejects(h.service.create(h.req),e=>e.status===409);});
test('event form has a bounded scroll, explicit editable date, and full-screen presentation',()=>{const form=fs.readFileSync('front/mi-front-limpio/screens/planner/EventForm.tsx','utf8');assert.ok(form.includes('style={S.scroll}'));assert.ok(form.includes('Cambiar fecha del evento:'));assert.ok(form.includes('Tocá la fecha para cambiarla.'));const host=fs.readFileSync('front/mi-front-limpio/components/planner/PlannerSheetHost.tsx','utf8');assert.ok(host.includes('accessibilityLabel="Volver al calendario"'));});
const ts=require('../front/mi-front-limpio/node_modules/typescript');
test('dirty dismissal preserves the draft until the user explicitly chooses discard',()=>{
 let choices,closed=0;const exports={};const code=ts.transpileModule(fs.readFileSync('front/mi-front-limpio/utils/requestDraftClose.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 vm.runInNewContext(code,{exports,require:()=>({Alert:{alert:(_title,_message,buttons)=>{choices=buttons;}}})});
 exports.requestDraftClose(false,()=>closed++);assert.equal(closed,1);
 exports.requestDraftClose(true,()=>closed++);assert.equal(closed,1);assert.equal(choices[0].style,'cancel');choices[1].onPress();assert.equal(closed,2);
});
