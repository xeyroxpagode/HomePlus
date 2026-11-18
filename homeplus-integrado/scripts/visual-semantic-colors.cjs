// Replace only reviewed legacy palette literals in presentation properties.
// Media-specific blacks/whites, charts and arbitrary category colors are retained.
const fs=require('node:fs'),path=require('node:path');
const ts=require('../front/mi-front-limpio/node_modules/typescript');
const root=path.resolve(__dirname,'..'),front=path.join(root,'front/mi-front-limpio');
const group=process.argv.find(x=>x.startsWith('--group='))?.slice(8),apply=process.argv.includes('--apply');
const groups={planner:['screens/planner','components/planner'],family:['components/family','screens/FamilyScreen','screens/presence','components/presence'],inventory:['screens/inventory'],assets:['screens/assets','components/assets'],cloud:['screens/HomeCloud','components/homecloud'],messages:['screens/messages','components/messages','screens/feed'],account:['screens/Profile','screens/Security','screens/Notification','screens/Experience','screens/Login','screens/Registro','screens/Forgot','screens/Update','screens/Splash','screens/AuthLoading','screens/P0','screens/CrearGrupo','screens/InvitarPersonas','screens/JoinHousehold','screens/simple','components/simple','components/Auth'],home:['screens/home','components/hplus'],shared:['components/ui']};
const map={
 '#e7643f':'brand','#c94f2e':'brandPressed','#ffe3da':'brandSoft',
 '#fcfbf9':'background.base','#fbfaf8':'background.base','#f4f0eb':'surface.soft',
 '#ded5cb':'border.default','#cdbfb3':'border.strong',
 '#ffe3e6':'danger.soft','#dcf7e8':'success.soft','#fff0d7':'warning.soft','#e1efff':'info.soft',
 '#d64c5a':'danger.base','#168a61':'success.base','#d98622':'warning.base','#3178c6':'info.base',
};
function walk(d){return fs.readdirSync(d,{withFileTypes:true}).flatMap(e=>e.isDirectory()?walk(path.join(d,e.name)):[path.join(d,e.name)]);}
const report=[];
for(const file of ['screens','components'].flatMap(d=>walk(path.join(front,d))).filter(f=>f.endsWith('.tsx')&&groups[group]?.some(p=>path.relative(front,f).replaceAll('\\','/').startsWith(p)))){
 const src=fs.readFileSync(file,'utf8'),sf=ts.createSourceFile(file,src,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),edits=[];
 function visit(n){
  if(ts.isPropertyAssignment(n)&&ts.isStringLiteral(n.initializer)){
   const key=n.name.getText(sf).replaceAll(/['"]/g,''),value=n.initializer.text.toLowerCase();
   if(['backgroundColor','color','borderColor','borderTopColor','borderBottomColor','borderLeftColor','borderRightColor','tintColor'].includes(key)){
    let token=map[value];
    if(['#fff','#ffffff','white'].includes(value)&&key==='backgroundColor')token='surface.card';
    if(['#1a1714','#1c1c1c','#1a1816','#111827','#111','#000','#000000','#222222'].includes(value)&&key==='color')token='text.primary';
    if(key==='color'&&value==='#4a4540')token='text.secondary';
    if(key==='color'&&value==='#6b6560')token='text.tertiary';
    if(key==='color'&&value==='#8a8178')token='text.muted';
    if(['#fafaf8','#fffaf5'].includes(value)&&key==='backgroundColor')token='background.base';
    if(key==='color'&&value==='#6b6b6b')token='text.secondary';
    if(token)edits.push({start:n.initializer.getStart(sf),end:n.initializer.end,text:`colors.${token}`,before:n.initializer.text,after:token});
   }
  }
  ts.forEachChild(n,visit);
 }
 visit(sf);if(!edits.length)continue;
 let hasColors=false;
 for(const s of sf.statements)if(ts.isImportDeclaration(s)&&/constants\/theme$/.test(s.moduleSpecifier.text))for(const e of s.importClause?.namedBindings?.elements||[])if(e.name.text==='colors')hasColors=true;
 // Dynamic factories already receive colors through their parameter/local binding.
 if(!hasColors&&!/\b(?:const|let)\s*\{[^}]*\bcolors\b|function\s+\w+\s*\(\s*\{[^}]*\bcolors\b/.test(src)){
  let rel=path.relative(path.dirname(file),path.join(front,'constants/theme')).replaceAll('\\','/');if(!rel.startsWith('.'))rel='./'+rel;
  edits.push({start:0,end:0,text:`import { colors } from '${rel}';\n`});
 }
 let result=src;for(const e of edits.sort((a,b)=>b.start-a.start))result=result.slice(0,e.start)+e.text+result.slice(e.end);
 const relative=path.relative(root,file).replaceAll('\\','/');report.push({file:relative,changes:edits.filter(e=>e.before)});
 if(apply){const backup=path.join(root,'artifacts/visual-v2/before',relative);if(!fs.existsSync(backup)){fs.mkdirSync(path.dirname(backup),{recursive:true});fs.writeFileSync(backup,src);}fs.writeFileSync(file,result);}
}
if(apply)fs.writeFileSync(path.join(root,`artifacts/visual-v2/${group}-semantic-colors.json`),JSON.stringify(report,null,2));
console.log(JSON.stringify({group,apply,files:report.length,changes:report.reduce((n,f)=>n+f.changes.length,0),paths:report.map(f=>f.file)},null,2));
