// Execute submitted predicate and actual ImageUtil resource dispatch method.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),cp=require('node:child_process');
const ts=require(process.env.AGENTLAB_ORACLE_TYPESCRIPT),root=process.argv[2],stage=Number(process.argv[3]);
if(![1,2].includes(stage))throw Error('Unsupported stage');
try {
const files=['common/src/main/ets/util/UrlUtil.ets','common/src/main/ets/util/ImageUtil.ets','common/src/main/ets/component/ImageComponent.ets','features/devpractices/src/main/ets/view/ImagePreview.ets'];
const analyze=f=>JSON.parse(cp.execFileSync(process.env.AGENTLAB_SOURCE_PROBE,[path.join(root,f)],{maxBuffer:8*1024*1024}));
const analyses=files.map(analyze),raw=fs.readFileSync(path.join(root,files[1]));
const method=analyses[1].rows.find(r=>r.kind==='symbol'&&r.owner==='ImageUtil'&&r.symbol==='getImgResource');if(!method)throw Error('Missing submitted resource method');
class PlatformURL extends URL {static parseURL(value){return new PlatformURL(value);}}
const context={exports:{},require:id=>{if(id!=='@kit.ArkTS')throw Error('Unexpected URL dependency '+id);return {url:{URL:PlatformURL}};},$r:name=>({resource:name}),$rawfile:name=>({rawfile:name})};vm.createContext(context);
const compile=s=>ts.transpileModule(s,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
vm.runInContext(compile(fs.readFileSync(path.join(root,files[0]),'utf8')),context);context.UrlUtil=context.exports.UrlUtil;
const submittedMethod=raw.subarray(method.span.startByte,method.span.endByte).toString();vm.runInContext(compile('class Caller {\n'+submittedMethod+'\n}\nthis.Caller=Caller;'),context);
const fixtures=[['https://example.com/a?x=1#part',true],['http://example.com/a',true],['HTTPS://EXAMPLE.COM/a',true],['https://',false],['http://',false],['http://example.com:99999/a',false],['https://bad host/a',false],[' https://example.com/a',false],['images/a.png',false],['file:///a.png',false],['data:image/png;base64,AA',false],['',false],[null,false]];
const checks={sourceSyntaxParsed:analyses.every(a=>!a.syntaxHasErrors)},observations=[];
fixtures.forEach(([input,expected],i)=>{const actual=context.UrlUtil.isNetUrl(input);checks['urlFixture'+i]=actual===expected;observations.push({input,expected,actual});});
if(stage===2){for(const [input,expected] of [['https://example.com/a?x=1#part','network'],['images/a.png','rawfile'],['https://','rawfile'],['','placeholder']]){const actual=context.Caller.getImgResource(input);checks['dispatch-'+expected+'-'+input]=expected==='network'?actual===input:expected==='rawfile'?actual?.rawfile===input:actual?.resource==='app.media.ic_placeholder';observations.push({input,dispatchExpected:expected,actual});}checks.previewUsesSharedPredicate=fs.readFileSync(path.join(root,files[3]),'utf8').includes('UrlUtil.isNetUrl(');checks.componentUsesSharedPredicate=fs.readFileSync(path.join(root,files[2]),'utf8').includes('UrlUtil.isNetUrl(');}
console.log(JSON.stringify({stage,pass:Object.values(checks).every(Boolean),checks,observations,submittedMethod,submittedUtilitySource:fs.readFileSync(path.join(root,files[0]),'utf8'),sourceAnalyses:analyses,actualMethodsExecuted:true,callerBodyExecuted:true,referenceTransformsApplied:false,adapter:'Actual predicate and ImageUtil body; Node URL models only the @kit.ArkTS parser seam; modeled resource factories',platformURLParserQualified:false,previewBodyExecuted:false,componentBodyExecuted:false,uiRenderingQualified:false}));
}catch(error){console.log(JSON.stringify({stage,pass:false,error:String(error),referenceTransformsApplied:false}));}
