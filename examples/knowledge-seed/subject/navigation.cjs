// Executes actual submitted controller/caller bodies. No reference patching.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const ts=require(process.env.AGENTLAB_ORACLE_TYPESCRIPT);
const root=process.argv[2],stage=Number(process.argv[3]);
const file='common/src/main/ets/routermanager/PageContext.ets';
const source=fs.readFileSync(path.join(root,file),'utf8');
const callerSource=fs.readFileSync(path.join(root,'features/devpractices/src/main/ets/view/PracticeHomeView.ets'),'utf8');
const logs=[];
class Stack {
 constructor(){this.entries=[];this.calls=[];this.fail=false;}
 call(op,args,apply){this.calls.push({op,args});if(this.fail)throw {code:7,message:'controlled failure'};apply();}
 pushPath(data,animated){this.call('push',[data,animated],()=>this.entries.push(data));}
 replacePath(data,animated){this.call('replace',[data,animated],()=>this.entries.splice(Math.max(0,this.entries.length-1),1,data));}
 pop(animated){this.call('pop',[animated],()=>this.entries.pop());}
 popToIndex(index,animated){this.call('popToIndex',[index,animated],()=>this.entries.splice(index+1));}
 clear(animated){this.call('clear',[animated],()=>this.entries.splice(0));}
}
const context={NavPathStack:Stack,Logger:{error:(...args)=>logs.push(args)},exports:{},PageEnum:{PRACTICES_VIEW:'practices'}};vm.createContext(context);
function execute(text){const out=ts.transpileModule(text,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS},reportDiagnostics:true});if(out.diagnostics.some(x=>x.category===ts.DiagnosticCategory.Error))throw Error('Transpile syntax error');vm.runInContext(out.outputText,context,{timeout:2000});}
try {
 const start=source.indexOf('const TAG =');if(start<0)throw Error('Controller boundary missing');
 execute(source.slice(start));const page=new context.exports.PageContext(),stack=page.navPathStack;
 const outcomes=[page.openPage({routerName:'first',param:{id:1}}),page.openPage({routerName:'second'},false),page.replacePage({routerName:'replacement'},false)];
 const checks={replacement:stack.entries.length===2&&stack.entries[1].name==='replacement',argsPreserved:stack.calls[0].args[1]===true&&stack.calls[1].args[1]===false&&stack.calls[2].args[1]===false&&stack.entries[0].param.id===1,sameStack:page.navPathStack===stack};
 outcomes.push(page.popPage(false));checks.pop=stack.entries.length===1;
 page.openPage({routerName:'third'});outcomes.push(page.popPageByIndex(0,false));checks.popToIndex=stack.entries.length===1;
 outcomes.push(page.clear(false));checks.clear=stack.entries.length===0;checks.successObservable=outcomes.every(x=>x===true);
 stack.fail=true;const failures=[page.openPage({routerName:'fail'}),page.replacePage({routerName:'fail'}),page.popPage(),page.popPageByIndex(0),page.clear()];
 checks.failureObservable=failures.every(x=>x===false);checks.failureKeepsStack=stack.entries.length===0;checks.errorsLogged=logs.length===5;
 if(stage===2){
  const a=callerSource.indexOf('  aboutToAppear('),b=callerSource.indexOf('  build()',a);if(a<0||b<0)throw Error('Caller lifecycle boundary missing');
  execute('class Caller { '+callerSource.slice(a,b)+' }\nthis.Caller=Caller;');
  const caller=new context.Caller();Object.assign(caller,{samplePageContext:page,scroller:{id:'scroller'},homeTabController:{id:'tabs'},navigationFailed:false});
  caller.aboutToAppear();checks.callerFailure=caller.navigationFailed===true;
  stack.fail=false;stack.entries.push({name:'previous'});caller.aboutToAppear();checks.callerSuccess=caller.navigationFailed===false;
  const last=stack.calls.at(-1);checks.callerArguments=last.op==='replace'&&last.args[1]===false&&last.args[0].param.scroller===caller.scroller&&last.args[0].param.homeTabController===caller.homeTabController;checks.callerReplacement=stack.entries.length===1&&stack.entries[0].name==='practices';
 }
 console.log(JSON.stringify({stage,pass:Object.values(checks).every(Boolean),checks,logs,calls:stack.calls,controllerSource:source,callerSource,actualControllerBodiesExecuted:true,actualCallerBodyExecuted:stage===2,referenceTransformApplied:false,platformStackQualified:false,uiRenderingQualified:false}));
}catch(error){console.log(JSON.stringify({stage,pass:false,error:String(error),referenceTransformApplied:false}));}
