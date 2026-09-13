// Original PageContext operation bodies against an explicit stack model.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=process.argv[2],mode=process.argv[3];
if(!['baseline','reference','wrong-stack'].includes(mode))throw Error('Unknown mode');
const source=fs.readFileSync(path.join(root,'common/src/main/ets/routermanager/PageContext.ets'),'utf8');
let adapted=source.slice(source.indexOf('const TAG ='))
  .replace('export class PageContext implements IPageContext','class PageContext')
  .replace('private readonly pathStack: NavPathStack','pathStack')
  .replace('public get navPathStack(): NavPathStack','get navPathStack()')
  .replaceAll('public ','').replaceAll('data: RouterParam','data')
  .replaceAll('animated: boolean','animated').replaceAll('index: number','index').replaceAll(': void','');
if(mode!=='baseline')adapted=adapted.replaceAll('    } catch (err) {','      return true;\n    } catch (err) {')
  .replace(/(Logger.error\(TAG, [^\n]+\);)/g,'$1\n      return false;');
if(mode==='wrong-stack')adapted=adapted.replace('this.pathStack.replacePath','this.pathStack.pushPath');
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
const context={NavPathStack:Stack,Logger:{error:(...args)=>logs.push(args)}};
vm.createContext(context);vm.runInContext(adapted+'\nthis.PageContext=PageContext;',context);
const page=new context.PageContext(),stack=page.navPathStack;
const outcomes=[page.openPage({routerName:'first',param:{id:1}}),page.openPage({routerName:'second'},false),
  page.replacePage({routerName:'replacement',param:{id:2}},false)];
const replacement=stack.entries.length===2 && stack.entries[1].name==='replacement';
const argsPreserved=stack.calls[0].args[1]===true && stack.calls[1].args[1]===false &&
  stack.calls[2].args[1]===false && stack.entries[0].param.id===1;
outcomes.push(page.popPage(false));const pop=stack.entries.length===1;
page.openPage({routerName:'third'});outcomes.push(page.popPageByIndex(0,false));
const popToIndex=stack.entries.length===1;
outcomes.push(page.clear(false));const clear=stack.entries.length===0;
stack.fail=true;const failures=[page.openPage({routerName:'fail'}),page.replacePage({routerName:'fail'}),
  page.popPage(),page.popPageByIndex(0),page.clear()];
const checks={replacement,argsPreserved,pop,popToIndex,clear,sameStack:page.navPathStack===stack,
  successObservable:outcomes.every(x=>x===true),failureObservable:failures.every(x=>x===false),
  failureKeepsStack:stack.entries.length===0,errorsLogged:logs.length===5};
const callerPath='features/devpractices/src/main/ets/view/PracticeHomeView.ets';
const caller=fs.readFileSync(path.join(root,callerPath),'utf8');
if(!caller.includes('this.samplePageContext.replacePage('))throw Error('Pinned caller changed');
console.log(JSON.stringify({mode,pass:Object.values(checks).every(Boolean),checks,calls:stack.calls,logs,
  adaptedSource:adapted,caller:{path:callerPath,source:caller,bodyExecuted:false,outcomeMappingImplemented:false},
  adapter:'Type-erased original PageContext bodies; operator stack model. Real caller only source-verified.',
  harmonyBuildQualified:false,platformStackQualified:false}));
