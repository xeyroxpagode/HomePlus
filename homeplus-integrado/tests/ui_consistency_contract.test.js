const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const ts = require('../front/mi-front-limpio/node_modules/typescript');
const front = path.resolve(__dirname, '../front/mi-front-limpio');
const read = f => fs.readFileSync(path.join(front, f), 'utf8');
const react = { createElement: (type, props, ...children) => ({ type, props: { ...props, children } }) };
function load(file, requireModule) {
 const exports = {};
 vm.runInNewContext(ts.transpileModule(read(file), {compilerOptions:{module:ts.ModuleKind.CommonJS, jsx:ts.JsxEmit.React, esModuleInterop:true}}).outputText,{exports,require:requireModule});
 return exports;
}
const tokens = load('constants/theme.ts', () => ({Platform:{OS:'android',select:v=>v.android??v.default}}));
function renderRow(colors, props) {
 const {Row} = load('components/ui/Row.tsx', name => name==='react' ? react : name==='react-native' ? {View:'View'} : name.includes('AppTheme') ? {useAppTheme:()=>({colors})} : name.includes('theme') ? tokens : name.includes('Interactive') ? {InteractivePressable:'Pressable'} : {AppText:'Text'});
 return Row(props);
}
test('shared rows retain task density, immediate press and canonical callbacks in both themes', () => {
 for(const colors of [tokens.colors,tokens.darkColors]) {
  let calls=0; const row=renderRow(colors,{title:'Objeto',onPress:()=>calls++,variant:'card'});
  assert.equal(row.type,'Pressable'); assert.equal(row.props.pressScale,1);
  assert.equal(row.props.style[0].minHeight,72);
  assert.equal(row.props.style[1].backgroundColor,colors.surface.soft);
  assert.equal(row.props.accessibilityRole,'button'); row.props.onPress(); assert.equal(calls,1);
 }
});
test('busy/disabled rows retain semantics; composed controls are not discarded', () => {
 const slot={type:'DomainActions'}; const row=renderRow(tokens.colors,{children:slot,onPress:()=>{},disabled:true,accessibilityState:{busy:true}});
 assert.equal(row.props.disabled,true);assert.equal(row.props.accessibilityState.busy,true);
 assert.equal(row.props.children[0],slot);
});
test('all eight comparable page headers consume the same native primitive', () => {
 for(const file of ['FamilyScreen.tsx','MoreScreen.tsx','finance/FinanceScreen.tsx','assets/AssetsListScreen.tsx','HomeCloudScreen.tsx','inventory/InventarioScreen.tsx','planner/PlannerScreen.tsx','feed/FeedFamiliarScreen.tsx']) assert.match(read('screens/'+file),/<AppPageHeader/);
 const family=read('screens/FamilyScreen.tsx');assert.match(family,/<AppPageHeader title="Familia"/);assert.doesNotMatch(family,/familyViewSelectorRail/);
 assert.match(read('components/family/FamilyViewSegmentedControl.tsx'),/backgroundColor: colors.surface.glass/);
});
test('domain row consumers reuse shared geometry instead of duplicating task geometry', () => {
 for(const file of ['components/assets/AssetRow.tsx','components/family/MemberRow.tsx','components/finance/ui/FinanceRows.tsx','screens/planner/PlannerTasksScreen.tsx','screens/inventory/InventarioScreen.tsx','screens/planner/PlannerAttentionActivityScreen.tsx']) assert.match(read(file),/<Row\b/);
 const press=read('components/ui/InteractivePressable.tsx');assert.match(press,/useReducedMotion\(\)/);assert.doesNotMatch(press,/AccessibilityInfo.addEventListener/);
});
test('press feedback precedes a deliberately delayed operation without faking success', async () => {
 const events=[];let finish;
 const pending=new Promise(resolve=>{finish=resolve});
 const reactHooks={...react,useRef:value=>({current:value}),useState:()=>[false,value=>events.push(value?'pressed':'released')],useEffect:()=>{}};
 const native={Pressable:'Pressable',Animated:{createAnimatedComponent:()=> 'NativePressable',Value:class{stopAnimation(){} setValue(){}},spring:()=>({start:()=>events.push('motion')})}};
 const {InteractivePressable}=load('components/ui/InteractivePressable.tsx',name=>name==='react'?reactHooks:name==='react-native'?native:name.includes('useReducedMotion')?{useReducedMotion:()=>false}:name.includes('haptics')?{}:tokens);
 const element=InteractivePressable({children:'Save',pressScale:1,onPress:async()=>{events.push('request');await pending;events.push('confirmed')}});
 element.props.onPressIn({});const operation=element.props.onPress({});
 assert.deepEqual(events,['pressed','request']);
 assert.equal(events.includes('confirmed'),false);finish();await operation;
 assert.deepEqual(events,['pressed','request','confirmed']);
 assert.equal(element.props.style[1].transform,undefined);
});

test('Planner form host bounds embedded footers to the keyboard-adjusted viewport', () => {
 const host=read('components/planner/PlannerSheetHost.tsx');
 assert.match(host, /Keyboard.addListener\('keyboardDidShow'/);
 assert.match(host, /paddingBottom: keyboardOverlap/);
 assert.match(host, /isFormSheet && \{ height: formHeight, minHeight: 0, maxHeight: '100%' \}/);
 assert.doesNotMatch(host, /height: Math.max\(360, viewportHeight/);
 assert.match(host, /contentManagesVerticalScroll \? content/);
});
