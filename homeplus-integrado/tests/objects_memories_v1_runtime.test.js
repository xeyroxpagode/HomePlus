const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const ts=require('../front/mi-front-limpio/node_modules/typescript');
const read=p=>fs.readFileSync(p,'utf8');
function photoHarness({deny=false,pickerError=false,fail=false}={}) {
 let created=0,runs=0,resolve;
 const done=new Promise(r=>resolve=r),jobs=[];
 const exports={};
 const source=ts.transpileModule(read('front/mi-front-limpio/services/homecloud/homecloudPhotoMemoryService.ts'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 const engine={createJob:(ctx,artifact)=>{created++;const j={id:'job',householdId:'h',intakeSource:ctx.intakeSource,artifact};jobs.push(j);return j},run:async()=>{runs++;if(fail)throw Error('network');await done;return {id:'job',state:'completed',contentId:'photo'}}};
 vm.runInNewContext(source,{exports,require:n=>n==='expo-image-picker'?{requestCameraPermissionsAsync:async()=>({granted:!deny}),launchCameraAsync:async()=>({canceled:true}),launchImageLibraryAsync:async()=>{if(pickerError)throw Error('picker');return {canceled:false,assets:[{uri:'file://photo.jpg',fileName:'photo.jpg',mimeType:'image/jpeg',fileSize:1200}]}}}:n.includes('DurableArtifact')?{copyArtifactToDurableWorkspace:async a=>a}:n.includes('UploadEngine')?{createUploadEngine:()=>engine,createFetchArtifactReader:()=>{},createExpoFileSystemUploadTransport:()=>{}}:n.includes('UploadJobStorage')?{getSharedUploadJobStore:()=>({get:()=>jobs.at(-1),all:()=>jobs,hydrate:async()=>{}})}:n.includes('UploadError')?{homeCloudUploadErrorMessage:()=> 'error'}:n.includes('Diagnostics')?{memoryDevTrace:()=>{}}:n.includes('Recovery')?{recoverUploadJobs:async()=>{}}:{fetchHomeCloudAlbumsCached:async()=>[]}});
 const service=exports.createPhotoMemoryUploadService({householdId:'h',accessToken:'test',capabilities:{contribute:!deny}});let state;service.subscribe(v=>state=v);
 return {service,state:()=>state,counts:()=>({created,runs}),finish:()=>resolve()};
}
test('selection shows preview without register/upload; confirm is single-flight even on double tap',async()=>{
 const h=photoHarness();await h.service.pick();assert.equal(h.state().status,'preview');assert.equal(h.counts().created,0);
 const saving=h.service.uploadSelected();await h.service.uploadSelected();assert.equal(h.state().status,'uploading');assert.equal(h.counts().created,1);
 h.finish();assert.equal(await saving,'photo');assert.equal(h.state().status,'completed');assert.equal(h.counts().runs,1);
});
test('discard never uploads; denied and picker failures never register',async()=>{
 const h=photoHarness();await h.service.pick();h.service.discardSelection();assert.equal(h.state().status,'idle');assert.equal(h.counts().created,0);
 for(const options of [{deny:true},{pickerError:true}]) {const x=photoHarness(options);await x.service.pick();assert.equal(x.state().status,'failed');assert.equal(x.counts().created,0);}
});
test('failed upload remains failed and retry retains the same job identity',async()=>{
 const h=photoHarness({fail:true});await h.service.pick();await h.service.uploadSelected();assert.equal(h.state().status,'failed');await h.service.retry();assert.equal(h.counts().created,1);assert.equal(h.counts().runs,2);assert.equal(h.state().status,'failed');
});
function trashHarness({allowed=true,row={id:'11111111-1111-4111-8111-111111111111',lifecycle:'active',household_id:'h1'}}={}) {
 const calls=[];let updated=0;
 const client={from:()=>{let filters={};const q={select:()=>q,eq:(key,value)=>{filters[key]=value;calls.push([key,value]);return q},maybeSingle:async()=>({data:row&&filters.household_id===row.household_id?row:null,error:null}),update:()=>{updated++;return q},then:resolve=>resolve({error:null})};return q}};
 const exports={},module={exports};vm.runInNewContext(read('backend/src/services/homecloudMemoriesService.js'),{exports,module,require:n=>n.includes('config/supabase')?{supabaseAdmin:client}:n.includes('context.service')?{getHomeCloudContext:async()=>({householdId:'h1',household:{},membership:{id:'m',role:'coordinator',status:'active'}})}:n.includes('Capabilities')?{resolveHomeCloudCapabilities:()=>({}),assertHomeCloudCapability:()=>{if(!allowed)throw Object.assign(Error('forbidden'),{status:403})}}:{createHttpError:(status,message)=>Object.assign(Error(message),{status})}});
 return {run:()=>module.exports.trashPhotoMemory({params:{contentId:'11111111-1111-4111-8111-111111111111'}}),calls,updated:()=>updated};
}
test('trash preserves household/role scope and is idempotent',async()=>{
 const h=trashHarness();assert.equal((await h.run()).trashed,true);assert.equal(h.updated(),1);assert.ok(h.calls.some(([k,v])=>k==='household_id'&&v==='h1'));assert.ok(h.calls.some(([k,v])=>k==='role'&&v==='memory'));
 const replay=trashHarness({row:{lifecycle:'trashed',household_id:'h1'}});await replay.run();assert.equal(replay.updated(),0);
});
test('trash rejects missing authority, other household, and pending content without writes',async()=>{
 for(const [options,status] of [[{allowed:false},403],[{row:{household_id:'h2',lifecycle:'active'}},404],[{row:{household_id:'h1',lifecycle:'staging'}},409]]) {const h=trashHarness(options);await assert.rejects(h.run(),e=>e.status===status);assert.equal(h.updated(),0);}
});

test('native upload resolves dependencies inside the Metro bundle and streams the file URI',async()=>{
 const exports={},calls=[];
 const source=ts.transpileModule(read('front/mi-front-limpio/services/homecloud/homecloudUploadEngine.ts'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 const native={FileSystemUploadType:{BINARY_CONTENT:0},uploadAsync:async(url,uri,options)=>{calls.push({url,uri,options});return {status:200}}};
 vm.runInNewContext(source,{exports,require:n=>n==='expo-file-system/legacy'?native:n.includes('SignedUrl')?{normalizeSignedStorageUrlForRuntime:u=>u}:{}});
 const transport=exports.createExpoFileSystemUploadTransport();
 assert.equal((await transport({signedUploadUrl:'https://storage.test/upload',localUri:'file://photo.jpg',mimeType:'image/jpeg'})).ok,true);
 assert.equal(calls[0].uri,'file://photo.jpg');assert.equal(calls[0].options.uploadType,0);
 assert.doesNotMatch(read('front/mi-front-limpio/services/homecloud/homecloudUploadEngine.ts'),/await import\('expo-file-system/);
 assert.doesNotMatch(read('front/mi-front-limpio/storage/homecloudUploadJobStorage.ts'),/await import\('@react-native-async-storage/);
});
test('private thumbnail cache does not reuse authorization across sessions or resurrect a cleared cache',async()=>{
 const exports={};let calls=0,release;
 const source=ts.transpileModule(read('front/mi-front-limpio/services/homecloud/homecloudMemoryPreview.ts'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 vm.runInNewContext(source,{exports,AbortController,require:()=>({fetchHomeCloudContentAccess:async()=>{calls++;if(release==='wait')await new Promise(r=>release=r);return {signedUrl:'https://private.test/photo',expiresIn:3600}}})});
 await exports.getMemoryPreviewUrl('session-a','photo');await exports.getMemoryPreviewUrl('session-a','photo');assert.equal(calls,1);
 await exports.getMemoryPreviewUrl('session-b','photo');assert.equal(calls,2);
 exports.clearMemoryPreviewCache();release='wait';const pending=exports.getMemoryPreviewUrl('session-a','photo');exports.clearMemoryPreviewCache();release();release=null;await pending;
 await exports.getMemoryPreviewUrl('session-a','photo');assert.equal(calls,4);
});
test('Objects reuse enlarged shared cards and seed only the current household detail before navigation',()=>{
 const row=read('front/mi-front-limpio/components/assets/AssetRow.tsx');assert.match(row,/<Row/);assert.match(row,/variant="card"/);assert.match(row,/size="detail"/);assert.match(row,/variant="body" weight="600"/);
 const screen=read('front/mi-front-limpio/screens/assets/AssetsListScreen.tsx');assert.ok(screen.indexOf('assetsCache.set(assetsKeys.detail')<screen.indexOf("navigation.navigate('AssetsDetail'"));
 assert.match(read('front/mi-front-limpio/hooks/assets/useAssetsData.ts'),/void runFetch\(true\)/);
});
test('remounted upload engines share one flight and reject joining it from another household',async()=>{
 const exports={};let calls=0,finish;let job={id:'job',householdId:'h1',role:'file',state:'finalizing',contentId:'content'};
 const source=ts.transpileModule(read('front/mi-front-limpio/services/homecloud/homecloudUploadEngine.ts'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 vm.runInNewContext(source,{exports,require:n=>n==='../api'?{OPERATION_KINDS:{NON_VERSIONED_MUTATION:'write'},requestJson:()=>{calls++;return new Promise(r=>finish=r)}}:n.endsWith('homecloudUploadJob')?{transition:(j,state)=>({...j,state}),guardOwnership:(j,scope)=>j.householdId===scope.householdId?null:'wrong household'}:{memoryDevTrace:()=>{}}});
 const store={get:()=>job,put:j=>{job=j}};const deps={store,getAccessToken:()=> 'test',getHouseholdId:()=> 'h1'};
 const a=exports.createUploadEngine(deps),b=exports.createUploadEngine(deps);
 const first=a.run('job'),second=b.run('job');assert.equal(calls,1);
 const foreign=exports.createUploadEngine({...deps,getHouseholdId:()=> 'h2'});await assert.rejects(foreign.run('job'),/wrong household/);
 finish({});await Promise.all([first,second]);assert.equal(job.state,'completed');assert.equal(calls,1);
});
