const fs=require('node:fs'),path=require('node:path');
const ts=require('../front/mi-front-limpio/node_modules/typescript');
const root=path.resolve(__dirname,'..'),front=path.join(root,'front/mi-front-limpio');
const apply=process.argv.includes('--apply');
const names={Home:'home',Planner:'planner',Bienes:'assets',Homi:'homi',HomeCloud:'files',Configuración:'settings'};
const approved={home:'Casa',planner:'Organizador',assets:'Objetos',homi:'Homie',files:'Archivos',settings:'Ajustes'};
const uiKeys=new Set(['title','label','subtitle','description','message','copy','body','heading','accessibilityLabel','accessibilityHint','placeholder','exitLabel','secondaryLabel','primaryLabel','emptyTitle','emptyDescription']);
function walk(d){return fs.readdirSync(d,{withFileTypes:true}).flatMap(e=>e.isDirectory()?walk(path.join(d,e.name)):[path.join(d,e.name)]);}
const report=[];
for(const file of ['screens','components','navigation'].flatMap(d=>walk(path.join(front,d))).filter(f=>/\.tsx?$/.test(f))){
 const src=fs.readFileSync(file,'utf8'),sf=ts.createSourceFile(file,src,ts.ScriptTarget.Latest,true,file.endsWith('tsx')?ts.ScriptKind.TSX:ts.ScriptKind.TS),edits=[];let needsImport=false;
 function visit(n){
  const isAssetSurface=/[\\/]assets[\\/]/.test(file);
  const isText=ts.isJsxText(n),isString=ts.isStringLiteral(n)||ts.isNoSubstitutionTemplateLiteral(n);
  if(isText||isString){
   const value=isText?n.getText(sf):n.text,p=n.parent;
   const ui=isText||(ts.isJsxAttribute(p)&&uiKeys.has(p.name.getText(sf)))||(ts.isPropertyAssignment(p)&&uiKeys.has(p.name.getText(sf).replaceAll(/['"]/g,'')))||ts.isJsxExpression(p)||(ts.isCallExpression(p)&&p.expression.getText(sf)==='Alert.alert');
   const prose=/\s/.test(value)&&/\b(Planner|HomeCloud|Bienes|Homi)\b/.test(value)&&!/[\\/]|\$\{|^\[/.test(value)&&!ts.isImportDeclaration(p);
   if(ui||prose||(isAssetSurface&&isString&&/\bbien(?:es)?\b/i.test(value))){
    if(isString&&ui&&names[value]){
     const expr=`productNames.${names[value]}`;edits.push({start:n.getStart(sf),end:n.end,text:ts.isJsxAttribute(p)?`{${expr}}`:expr,before:value,after:approved[names[value]]});needsImport=true;
    }else{
     let target=value.replace(/\bPlanner\b/g,'Organizador').replace(/\bHomeCloud\b/g,'Archivos').replace(/\bBienes\b/g,'Objetos').replace(/\bHomi\b/g,'Homie');
     if(ui&&!/Configuración (del|de) (iPhone|Android|dispositivo|teléfono|sistema)/.test(target))target=target.replace(/\bConfiguración\b/g,'Ajustes');
     if(ui)target=target.replace(/\bHome\b/g,'Casa').replace(/\blos activos\b/g,'los objetos').replace(/\bActivo no encontrado\b/g,'Objeto no encontrado').replace(/\bNuevo activo\b/g,'Nuevo objeto');
     if(isAssetSurface)target=target.replace(/\bbienes\b/g,'objetos').replace(/\bbien\b/g,'objeto').replace(/\bBienes\b/g,'Objetos').replace(/\bBien\b/g,'Objeto');
     if(target!==value)edits.push({start:n.getStart(sf),end:n.end,text:isText?target:JSON.stringify(target),before:value,after:target});
    }
   }
  }
  ts.forEachChild(n,visit);
 }
 visit(sf);if(!edits.length)continue;
 if(needsImport&&!/import[^;]*\bproductNames\b[^;]*from/.test(src)){let rel=path.relative(path.dirname(file),path.join(front,'constants/productLanguage')).replaceAll('\\','/');if(!rel.startsWith('.'))rel='./'+rel;edits.push({start:0,end:0,text:`import { productNames } from '${rel}';\n`});}
 let result=src;for(const e of edits.sort((a,b)=>b.start-a.start))result=result.slice(0,e.start)+e.text+result.slice(e.end);
 const relative=path.relative(root,file).replaceAll('\\','/');report.push({file:relative,changes:edits.filter(e=>e.before).map(e=>({before:e.before,after:e.after}))});
 if(apply){const backup=path.join(root,'artifacts/visual-v2/before',relative);if(!fs.existsSync(backup)){fs.mkdirSync(path.dirname(backup),{recursive:true});fs.writeFileSync(backup,src);}fs.writeFileSync(file,result);}
}
if(apply)fs.writeFileSync(path.join(root,'artifacts/visual-v2/naming-migration.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify({apply,files:report.length,changes:report.reduce((n,r)=>n+r.changes.length,0),preview:report.slice(0,8)},null,2));
