const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const ts = require('../front/mi-front-limpio/node_modules/typescript');
const front = path.resolve(__dirname, '../front/mi-front-limpio');
const read = file => fs.readFileSync(path.join(front, file), 'utf8');
const react = { createElement: (type, props, ...children) => ({type, props: {...props, children}}) };
const theme = {spacing: {1:4,2:8,3:12,4:16,6:24}, touchTargets:{normal:44}, radius:{xxl:24}};
function load(file, dimensions = {width:393,fontScale:1}) {
 const exports = {};
 vm.runInNewContext(ts.transpileModule(read(file),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React,esModuleInterop:true}}).outputText, {exports, require:name => name==='react' ? react : name==='react-native' ? {View:'View',StyleSheet:{create:v=>v},useWindowDimensions:()=>dimensions} : name.includes('AppTheme') ? {useAppTheme:()=>({colors:{sand:{50:'#eee'}}})} : name.includes('theme') ? theme : name.endsWith('AppText') ? {AppText:'Text'} : {AppButton:'Button'}});
 return exports;
}
test('header fills constrained parents and gives remaining width to title, preserving actions',()=>{
 const {AppPageHeader}=load('components/ui/AppPageHeader.tsx');
 const back={type:'Back'}, action={type:'Menu'};
 const tree=AppPageHeader({title:'Finanzas',leading:back,action,singleLineTitle:true});
 assert.equal(tree.props.style[0].alignSelf,'stretch');
 const row=tree.props.children[1];
 const [left,copy,right]=row.props.children;
 assert.equal(left.props.style.flex,undefined);assert.equal(right.props.style.flex,undefined);
 assert.equal(left.props.style.minWidth,44);assert.equal(right.props.style.minWidth,44);
 assert.equal(copy.props.style.flex,1);assert.equal(left.props.children[0],back);assert.equal(right.props.children[0],action);
 const title=copy.props.children[0];assert.equal(title.props.children[0],'Finanzas');assert.equal(title.props.numberOfLines,1);
});
test('large accessibility type gets full-width heading without losing add or back controls',()=>{
 for(const dimensions of [{width:320,fontScale:1},{width:320,fontScale:1.6},{width:393,fontScale:2}]) {
  const {AppPageHeader}=load('components/ui/AppPageHeader.tsx',dimensions);
  const add={type:'Add'};const tree=AppPageHeader({title:'Organizador',action:add,singleLineTitle:true});
  assert.equal(tree.props.children[0].props.children[0],'Organizador');
  assert.equal(tree.props.children[1].props.children[1].props.children[0],null);
  assert.equal(tree.props.children[1].props.children[2].props.children[0],add);
 }
});
test('compact empty state is secondary unframed copy, while default actions remain available',()=>{
 const {EmptyState}=load('components/ui/EmptyState.tsx');
 const compact=EmptyState({title:'Sin actividades próximas',variant:'compact'});
 const style=compact.props.style[0];assert.equal(style.padding,0);assert.equal(style.paddingVertical,8);
 assert.equal(style.backgroundColor,undefined);assert.equal(style.borderWidth,undefined);
 const title=compact.props.children[1].props.children[0];assert.equal(title.props.variant,'bodySmall');assert.equal(title.props.tone,'secondary');
 let called=0;const normal=EmptyState({title:'Vacío',description:'Descripción',actionLabel:'Agregar',onAction:()=>called++});
 assert.equal(normal.props.style[0].padding,24);normal.props.children[2].props.onPress();assert.equal(called,1);
});
test('Casa compact empties exclude loading and errors; content and contextual links are retained',()=>{
 const source=read('screens/home/HomePlannerSections.tsx');
 assert.match(source,/canConfirmPlannerEmpty = Boolean\(summary\) && !hasPartial && \(status === 'ready' \|\| status === 'empty'\)/);
 assert.match(source,/todayEmpty = !plannerLoading && !daily.loading && canConfirmPlannerEmpty\s*&& !daily.schedulesError/);
 assert.match(source,/upcomingEmpty = !plannerLoading && canConfirmPlannerEmpty/);
 assert.match(source,/activityEmpty = !daily.loading && !daily.activityError/);
 for(const key of ['todayEmpty','upcomingEmpty','activityEmpty']) assert.match(source,new RegExp('\\{'+key+' \\? <EmptyState variant="compact"'));
 for(const content of ['visibleTodayTasks.map','todayEvents.map','todaySchedules.map','upcomingEvents.map','upcomingTasks.map','daily.activity.map','No se pudo actualizar la actividad.','Ver calendario','Ver actividad']) assert.ok(source.includes(content),content);
});
