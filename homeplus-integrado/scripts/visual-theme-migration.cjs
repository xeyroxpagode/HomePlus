// Scoped mechanical migration: move existing style definitions into theme factories.
// No navigation, services, requests, state or domain expressions are rewritten.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const ts = require('../front/mi-front-limpio/node_modules/typescript');
const root = path.resolve(__dirname, '..');
const front = path.join(root, 'front/mi-front-limpio');
const group = process.argv.find(x => x.startsWith('--group='))?.slice(8) || 'planner';
const apply = process.argv.includes('--apply');
const groups = {
  planner: ['screens/planner', 'components/planner'],
  family: ['components/family', 'screens/FamilyScreen.tsx', 'screens/presence', 'components/presence'],
  inventory: ['screens/inventory'],
  assets: ['screens/assets', 'components/assets'],
  cloud: ['screens/HomeCloud', 'components/homecloud'],
  messages: ['screens/messages', 'components/messages', 'screens/feed'],
  account: ['screens/ProfileScreen.tsx', 'screens/SecuritySettingsScreen.tsx', 'screens/NotificationSettingsScreen.tsx', 'screens/ExperienceSelectorScreen.tsx', 'screens/Login.tsx', 'screens/Registro.tsx', 'screens/ForgotPassword.tsx', 'screens/UpdatePassword.tsx', 'screens/Splash.tsx', 'screens/AuthLoading.tsx', 'screens/P0', 'screens/CrearGrupo', 'screens/InvitarPersonas', 'screens/JoinHousehold', 'components/Auth', 'components/simple', 'screens/simple'],
  home: ['screens/home', 'components/hplus'],
  shared: ['components/ui'],
};
function walk(dir) { return fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => e.isDirectory() ? walk(path.join(dir,e.name)) : [path.join(dir,e.name)]); }
const files = [...walk(path.join(front,'screens')), ...walk(path.join(front,'components'))].filter(f => /\.tsx$/.test(f) && groups[group]?.some(p => path.relative(front,f).replaceAll('\\','/').startsWith(p)));
const manifest = [];
for (const file of files) {
  const src = fs.readFileSync(file,'utf8');
  const sf = ts.createSourceFile(file,src,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  const edits=[]; const factories=[]; const components=[]; const sharedFactories=[];
  const importedTheme = new Set();
  for (const s of sf.statements) if(ts.isImportDeclaration(s) && /constants\/theme$/.test(s.moduleSpecifier.text)) {
    for(const spec of s.importClause?.namedBindings?.elements||[]) if(!spec.propertyName) importedTheme.add(spec.name.text);
  }
  for (const s of sf.statements) if(ts.isImportDeclaration(s) && /plannerShared$/.test(s.moduleSpecifier.text)) {
    for(const spec of s.importClause?.namedBindings?.elements||[]) if((spec.propertyName?.text||spec.name.text)==='plannerStyles') {
      sharedFactories.push({name:spec.name.text,factory:'createPlannerStyles'});
      if(!s.importClause.namedBindings.elements.some(e=>e.name.text==='createPlannerStyles'))edits.push({start:s.importClause.namedBindings.getStart(sf)+1,end:s.importClause.namedBindings.getStart(sf)+1,text:' createPlannerStyles, '});
    }
  }
  for(const s of sf.statements) if(ts.isVariableStatement(s)) for(const d of s.declarationList.declarations) {
    if(ts.isIdentifier(d.name) && d.initializer && ts.isCallExpression(d.initializer) && d.initializer.expression.getText(sf)==='StyleSheet.create') {
      const expr=d.initializer.getText(sf);
      const tokens=['colors','shadows'].filter(t=>importedTheme.has(t) && new RegExp('\\b'+t+'\\b').test(expr));
      if(!tokens.length) continue;
      factories.push({name:d.name.text, factory:`create${d.name.text[0].toUpperCase()}${d.name.text.slice(1)}ForTheme`,tokens,expr,d});
    }
  }
  function findFn(n) {
    if(ts.isArrowFunction(n)||ts.isFunctionExpression(n)) return n;
    if(ts.isCallExpression(n)) for(const a of n.arguments) {const found=findFn(a);if(found)return found;}
    return null;
  }
  for(const s of sf.statements) {
    if(ts.isFunctionDeclaration(s)&&s.name&&/^[A-Z]/.test(s.name.text)&&s.body)components.push({name:s.name.text,fn:s});
    if(ts.isVariableStatement(s))for(const d of s.declarationList.declarations) if(ts.isIdentifier(d.name)&&/^[A-Z]/.test(d.name.text)&&d.initializer){const fn=findFn(d.initializer);if(fn&&ts.isBlock(fn.body))components.push({name:d.name.text,fn});}
  }
  let usesHook=false;
  for(const c of components) {
    const body=c.fn.body; const text=body.getText(sf);
    const names=new Set(); function bindings(n){if(ts.isVariableDeclaration(n)){if(ts.isIdentifier(n.name))names.add(n.name.text); else if(ts.isObjectBindingPattern(n.name))for(const e of n.name.elements)if(ts.isIdentifier(e.name))names.add(e.name.text);}if(ts.isParameter(n)&&ts.isIdentifier(n.name))names.add(n.name.text);if(n===body||!(ts.isFunctionLike(n)))ts.forEachChild(n,bindings);}bindings(body);
    const liveTokens=['colors','shadows'].filter(t=>importedTheme.has(t)&&!names.has(t)&&new RegExp('\\b'+t+'\\s*[.[]').test(text));
    const liveFactories=[...factories,...sharedFactories].filter(f=>!names.has(f.name)&&new RegExp('\\b'+f.name+'\\s*[.[]').test(text));
    if(!liveTokens.length&&!liveFactories.length)continue;
    let code='';
    if(liveTokens.length)code+=`\n  const { ${liveTokens.join(', ')} } = useAppTheme();`;
    for(const f of liveFactories)code+=`\n  const ${f.name} = useThemeStyles(${f.factory});`;
    edits.push({start:body.getStart(sf)+1,end:body.getStart(sf)+1,text:code+'\n'});usesHook=true;
  }
  if(!usesHook)continue;
  for(const f of factories) {
    edits.push({start:f.d.initializer.getStart(sf),end:f.d.initializer.end,text:`${f.factory}(lightTheme)`});
    edits.push({start:sf.end,end:sf.end,text:`\nfunction ${f.factory}({ ${f.tokens.join(', ')} }: Pick<AppResolvedTheme, ${f.tokens.map(t=>`'${t}'`).join(' | ')}>) {\n  return ${f.expr};\n}\n`});
  }
  const relativeTheme=path.relative(path.dirname(file),path.join(front,'context/AppThemeContext')).replaceAll('\\','/');
  const relativeHook=path.relative(path.dirname(file),path.join(front,'hooks/useThemeStyles')).replaceAll('\\','/');
  const relativeConstants=path.relative(path.dirname(file),path.join(front,'constants/theme')).replaceAll('\\','/');
  let imports='';
  if(!/import[^;]*\buseAppTheme\b[^;]*from\s+['"][^'"]*AppThemeContext['"]/.test(src))imports+=`import { useAppTheme } from '${relativeTheme.startsWith('.')?relativeTheme:'./'+relativeTheme}';\n`;
  if((factories.length||sharedFactories.length)&&!src.includes('import { useThemeStyles }'))imports+=`import { useThemeStyles } from '${relativeHook.startsWith('.')?relativeHook:'./'+relativeHook}';\n`;
  if(factories.length)imports+=`import { theme as lightTheme, type AppResolvedTheme } from '${relativeConstants.startsWith('.')?relativeConstants:'./'+relativeConstants}';\n`;
  edits.push({start:0,end:0,text:imports});
  let result=src;for(const e of edits.sort((a,b)=>b.start-a.start))result=result.slice(0,e.start)+e.text+result.slice(e.end);
  const relative=path.relative(root,file).replaceAll('\\','/');
  manifest.push({file:relative,components:components.map(c=>c.name),factories:factories.map(f=>f.name),beforeSha256:crypto.createHash('sha256').update(src).digest('hex')});
  if(apply) {
    const backup=path.join(root,'artifacts/visual-v2/before',relative);
    if(!fs.existsSync(backup)){fs.mkdirSync(path.dirname(backup),{recursive:true});fs.writeFileSync(backup,src);}
    fs.writeFileSync(file,result);
  }
}
if(apply){const dir=path.join(root,'artifacts/visual-v2');fs.mkdirSync(dir,{recursive:true});fs.writeFileSync(path.join(dir,`${group}-migration.json`),JSON.stringify(manifest,null,2));}
console.log(JSON.stringify({group,apply,count:manifest.length,files:manifest.map(x=>({file:x.file,factories:x.factories}))},null,2));
