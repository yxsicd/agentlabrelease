"""Real staged navigation assessment, with explicit source-only fresh-Agent fork."""
import argparse,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'real-code-agent'))
from participant import Participant
PIN='7aa95cac4eca15e39fc6638cdf1de7db6fb70ad6'
PATHS=['common/src/main/ets/routermanager/PageContext.ets','common/src/main/ets/model/PageEnum.ets','common/src/main/ets/util/Logger.ets','features/devpractices/src/main/ets/view/PracticeHomeView.ets']
DEMANDS=[
 'Expose boolean success/failure outcomes for PageContext navigation operations, including its interface. Preserve stack ownership, push/replace/pop/clear semantics, parameters, animation defaults and error logging. Keep valid ArkTS.',
 'Preserve all previous navigation behavior. In PracticeHomeView use @State navigationFailed: boolean = false; aboutToAppear must set it from the actual replacePage failure outcome and clear it on success. Preserve caller parameters and false animation. Do not install dependencies or change build configuration.']
FEEDBACK_DEMANDS=[
 "In FeedbackSheet preserve choices, input and open sheet while submitting and on rejection; reset and close only after success. Add @State submitting: boolean = false and @State submitError: string = ''; record the rejection message, release submitting on both outcomes and clear the error when retry starts. Preserve original submit parameters and invalid-input blocking. Keep valid ArkTS; do not install dependencies or change build configuration.",
 "Preserve all previous feedback failure/retry/reset behavior. While a submission is pending, repeated handleSubmit calls must produce exactly one SubmitInfoUtil request. Keep pending state and original parameters; after rejection a retry must be allowed and after success invalid input must remain blocked. Do not install dependencies or change build configuration."]
LOADING_DEMANDS=[
 'In DelayedLoadingView make each aboutToAppear start hidden and cancel any previous pending timer before scheduling a new one. aboutToDisappear must cancel pending work and release delayTimer to -1. Preserve @State showLoading: boolean = false, delayTimer: number = -1 and the existing delays for all five known breakpoints. Keep valid ArkTS; do not install dependencies or change build configuration.',
 'Preserve all previous delayed-loading behavior. In shared BreakpointType.getValue make unknown breakpoint values fall back to sm, preserving xs/sm/md/lg/xl and constructor optional xs/xl fallbacks. DelayedLoadingView must use the small delay for an unknown breakpoint; LoadingView must continue using the shared helper and existing resource mapping. Do not install dependencies or change build configuration.']
DEBOUNCE_DEMANDS=[
 'Fix DebounceUtil.debounce so every returned handler owns an independent accepted-click timestamp. The first call must execute immediately even at clock zero. Preserve the default 1000ms wait, suppress only its own repeats, accept at the exact wait boundary, and do not extend the accepted-click window on suppressed calls. Preserve ComponentBaseView click payloads and codelab forwarding. Keep valid ArkTS; do not install dependencies or change build configuration.',
 'Preserve all previous debounce behavior. Verify repeated suppressed clicks cannot postpone acceptance: with wait 100, accepted at time 2000, suppressed at 2050 and 2099, acceptance must occur at 2100 and next at 2200. Preserve independent component handlers, codelab forwarding and the default wait. Do not install dependencies or change build configuration.']
IMAGE_URL_DEMANDS=[
 'Fix UrlUtil.isNetUrl to recognize only valid HTTP/HTTPS URLs with a nonempty host. Preserve mixed-case schemes and query/fragment URLs; reject missing hosts, invalid ports, whitespace, relative paths and file/data URLs. Use the existing @kit.ArkTS URL API and preserve maskUrl behavior. Keep valid ArkTS; do not install dependencies or change build configuration.',
 'Preserve all previous URL classification behavior. Verify ImageUtil.getImgResource uses the shared predicate: valid network strings remain byte-for-byte unchanged, local paths and malformed network strings route to rawfile, empty input routes to the placeholder. Preserve ImageComponent and ImagePreview use of the shared predicate. Do not install dependencies or change build configuration.']
# Cache contract is consumed directly from the frozen TableGit exchange snapshot.
CACHE_CASE=next(json.loads(line) for line in (Path(__file__).resolve().parents[1]/'seeds/harmony-code-workshop/evaluation_cases.jsonl').read_text().split('\n') if line.strip() and json.loads(line)['id']=='case-cache-durability-subject-v1')
SCENARIOS={
 'cache-durability':dict(paths=CACHE_CASE['paths'],demands=CACHE_CASE['demands'],caseId=CACHE_CASE['id'],oracle='cache-durability.cjs',scope=CACHE_CASE['assessmentScope']),
 'debounce':dict(paths=['common/src/main/ets/util/DebounceUtil.ets','features/componentlibrary/src/main/ets/view/ComponentBaseView.ets','common/src/main/ets/util/index.ets'],demands=DEBOUNCE_DEMANDS,caseId='case-debounce-subject-v1',oracle='debounce.cjs',scope='Actual independent click handlers and accepted-click windows; full phone compile and selected-source fresh-Agent branch'),
 'image-url':dict(paths=['common/src/main/ets/util/UrlUtil.ets','common/src/main/ets/util/ImageUtil.ets','common/src/main/ets/component/ImageComponent.ets','features/devpractices/src/main/ets/view/ImagePreview.ets'],demands=IMAGE_URL_DEMANDS,caseId='case-image-url-subject-v1',oracle='image-url.cjs',scope='Actual URL predicate and ImageUtil resource dispatch; modeled platform parser/resource seams, full phone compile and selected-source fresh-Agent branch'),
 'loading':dict(paths=['common/src/main/ets/view/DelayedLoadingView.ets','common/src/main/ets/util/BreakpointSystem.ets','common/src/main/ets/view/LoadingView.ets'],demands=LOADING_DEMANDS,caseId='case-loading-subject-v1',oracle='loading.cjs',scope='Actual loading lifecycle/shared breakpoint methods and full phone compile; selected-source fresh-Agent branch'),
 'navigation':dict(paths=PATHS,demands=DEMANDS,caseId='case-navigation-subject-v1',oracle='navigation.cjs',scope='Actual navigation controller/caller methods and full phone compile; selected-source fresh-Agent branch'),
 'feedback':dict(paths=['common/src/main/ets/component/FeedbackSheet.ets','common/src/main/ets/model/FeedbackData.ets','common/src/main/ets/util/SubmitInfoUtil.ets','common/src/main/ets/component/Toast.ets'],demands=FEEDBACK_DEMANDS,caseId='case-feedback-subject-v1',oracle='feedback.cjs',scope='Actual feedback submit/reset methods with controlled Promise backend and full phone compile; selected-source fresh-Agent branch')}
def dump(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def sha256_file(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--scenario',choices=SCENARIOS,default='navigation');p.add_argument('--source',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--install-root',type=Path,required=True);p.add_argument('--pi-runtime',type=Path,required=True);p.add_argument('--image',required=True);p.add_argument('--build-cache-probe-only',action='store_true');p.add_argument('--retain-hap-bytes',action='store_true');a=p.parse_args()
 scenario=SCENARIOS[a.scenario];paths=scenario['paths'];demands=scenario['demands']
 experiment_started=time.monotonic_ns()
 root=a.root.resolve();root.mkdir();e=root/'evidence';e.mkdir();project=root/'workspace'
 subprocess.run(['git','clone','--no-hardlinks',str(a.source.resolve()),str(project)],check=True,capture_output=True)
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=project,text=True).strip()==PIN
 lock=json.loads((a.install_root/'downloads/environment-lock.json').read_text());dump(e/'environment-lock.json',lock)
 seed=json.loads(next(line for line in (Path(__file__).resolve().parents[1]/'seeds/harmony-code-workshop/evaluation_cases.jsonl').read_text().split('\n') if line.strip() and json.loads(line)['id']==scenario['caseId']));assert seed['demands']==demands
 dump(e/'frozen-task.json',seed)
 if seed.get('oracleDigest'):assert hashlib.sha256(Path(__file__).with_name(scenario['oracle']).read_bytes()).hexdigest()==seed['oracleDigest']
 summary=dict(schema='agentlab.'+a.scenario+'_subject.v1',taskId=scenario['caseId'],assessmentScope=scenario['scope'],sourceRevision=PIN,demands=demands,sourceForkQualified=False,formalSessionFSForkQualified=False,uiDeviceQualified=False,phases={},timing=dict(builds=[]),ok=False,subjectTaskSucceeded=False)
 def oracle(label,directory,stage):
  command=['node',str(Path(__file__).with_name(scenario['oracle'])),str(directory),str(stage)]
  r=subprocess.run(command,capture_output=True);(e/(label+'-oracle.stdout.json')).write_bytes(r.stdout);(e/(label+'-oracle.stderr.log')).write_bytes(r.stderr)
  if r.returncode:raise RuntimeError('Harness oracle infrastructure error')
  return json.loads(r.stdout)
 def cut(label,directory):
  out=e/label;out.mkdir();rows=[]
  for name in paths:
   if not (directory/name).is_file():rows.append(dict(path=name,absent=True));continue
   raw=(directory/name).read_bytes();target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);rows.append(dict(path=name,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
  delta=subprocess.run(['git','diff','--binary',PIN],cwd=directory,capture_output=True,check=True);(out/'workspace-tracked-delta.patch').write_bytes(delta.stdout)
  status=subprocess.run(['git','status','--porcelain'],cwd=directory,capture_output=True,check=True);(out/'workspace-status.txt').write_bytes(status.stdout)
  identity=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest();dump(out/'source-cut.json',dict(kind='source-only-cut',id=identity,files=rows));return identity
 def scope(label,directory):
  tracked=subprocess.check_output(['git','diff','--name-only',PIN,'--'],cwd=directory,text=True).splitlines()
  untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=directory,text=True).splitlines()
  raw=sorted(set(tracked+untracked));generated_prefixes=('.native-build/','.native-dependencies/','.hvigor/','build/','oh_modules/','node_modules/')
  generated=[name for name in raw if name.startswith(generated_prefixes)];changed=[name for name in raw if name not in generated]
  expected=set(paths);extra=[name for name in changed if name not in expected]
  result=dict(schema='agentlab.scope_drift.v2',label=label,expectedPaths=paths,rawChangedPaths=raw,generatedPaths=generated,changedPaths=changed,extraPaths=extra,changedCount=len(changed),extraCount=len(extra),drift=bool(extra))
  dump(e/(label+'-scope.json'),result);return result
 def generated_inventory(label,directory):
  candidates=['.hvigor','phone/build','build','oh_modules','node_modules']
  rows=[]
  for name in candidates:
   path=directory/name
   files=bytes_=0
   if path.exists():
    for base,_,names in os.walk(path):
     for entry in names:
      item=Path(base)/entry
      try:bytes_+=item.stat().st_size;files+=1
      except FileNotFoundError:pass
   rows.append(dict(path=name,exists=path.exists(),files=files,bytes=bytes_))
  result=dict(schema='agentlab.harmony_generated_inventory.v1',label=label,rows=rows,totalBytes=sum(x['bytes'] for x in rows))
  dump(e/(label+'-generated-inventory.json'),result);return result
 def task_prompt(demand):
  allowed='\n'.join('- '+name for name in paths)
  return demand+'\n\nAssessed edit boundary (frozen task paths):\n'+allowed+'\nYou may read other files for context, but do not modify files outside this list. If you believe another file must change, leave it unchanged and report the reason instead. Out-of-scope writes are independently measured.'
 sdk=next(x for x in lock['components'] if x['slot']=='harmony-cli');kit=next(x for x in lock['components'] if x['slot']=='harmony-build-kit')
 build_cache=Path(os.environ['AGENTLAB_HARMONY_BUILD_CACHE_HOST']).resolve();build_cache.mkdir(parents=True,exist_ok=True)
 fast_cli=os.environ.get('AGENTLAB_FAST_HARMONY_ROOT');fast_kit=os.environ.get('AGENTLAB_FAST_BUILD_KIT_ROOT')
 if bool(fast_cli)!=bool(fast_kit):raise RuntimeError('FAST_TOOLCHAIN_PAIR_REQUIRED')
 toolchain_mounts=(['--mount',f'type=bind,src={Path(fast_cli).resolve()},dst=/toolchains/harmony,readonly','--mount',f'type=bind,src={Path(fast_kit).resolve()},dst=/toolchains/harmony-build-kit,readonly'] if fast_cli else ['--mount',f'type=volume,src={sdk["volume"]},dst=/toolchains/harmony,readonly','--mount',f'type=volume,src={kit["volume"]},dst=/toolchains/harmony-build-kit,readonly'])
 base=['docker','run','--rm','--network=none']+toolchain_mounts+['--mount',f'type=bind,src={root},dst=/case','--mount',f'type=bind,src={build_cache},dst=/runtime/toolchain-cache/subject','--env','HARMONY_TOOLCHAIN_ROOT=/toolchains/harmony','--env','HARMONY_BUILD_CACHE=/runtime/toolchain-cache/subject','--entrypoint','/usr/bin/python3',lock['images'][0]['reference'],'/toolchains/harmony-build-kit/bin/harmony']
 def build(label,directory,prepare=False):
  command=[x for x in base if not (prepare and x=='--network=none')]+['prepare-deps' if prepare else 'build','--project','/case/'+directory.name]
  if not prepare:command+=['--module','phone','--offline']
  started=time.monotonic_ns();started_ms=(started-experiment_started)//1_000_000
  dump(e/(label+'-command.json'),command);r=subprocess.run(command,capture_output=True,timeout=660 if prepare else 240);duration_ms=(time.monotonic_ns()-started)//1_000_000;(e/(label+'-stdout.log')).write_bytes(r.stdout);(e/(label+'-stderr.log')).write_bytes(r.stderr)
  summary['timing']['builds'].append(dict(label=label,prepare=prepare,startedMs=started_ms,durationMs=duration_ms,success=r.returncode==0))
  if not prepare and 'firstCompileStartMs' not in summary['timing']:summary['timing']['firstCompileStartMs']=started_ms
  reports=directory/('.native-dependencies' if prepare else '.native-build')
  if reports.exists():shutil.copytree(reports,e/label)
  if r.returncode==0 and not prepare:
   report=json.loads((reports/'result.json').read_text());out=root/'full-hap'
   if a.retain_hap_bytes:out.mkdir(exist_ok=True)
   for item in report['artifacts']:
    hap=directory/item['path'];assert sha256_file(hap)==item['sha256']
    name=label+'-'+hap.name
    if a.retain_hap_bytes:shutil.copy2(hap,out/name)
    manifest=e/'binary-manifest.json';rows=json.loads(manifest.read_text()) if manifest.exists() else []
    rows.append(dict(label=label,filename=name,sha256=item['sha256'],bytes=item['bytes'],module=item['module'],retainedBytes=a.retain_hap_bytes));dump(manifest,rows)
  return r.returncode==0
 def subject(name):
  pe=e/name;pe.mkdir();runtime=root/(name+'-runtime');runtime.mkdir();session=runtime/'session';session.mkdir();wrapper=runtime/'container-pi.py';shutil.copy2(Path(__file__).with_name('container-pi.py'),wrapper)
  dump(runtime/'container-launch.json',dict(runtime=str(a.pi_runtime.resolve()),session=str(session),image=a.image))
  return Participant(pe,runtime/'state',wrapper,os.environ['AGENTLAB_LM_GATEWAY_URL'],os.environ.get('AGENTLAB_MODEL','glm-5.3-flash'))
 parent=None;fork=None
 try:
  if a.build_cache_probe_only:
   if not build('prepare',project,True):raise RuntimeError('Harness dependency preparation failed')
   compiled=build('build-cache-probe',project)
   summary['phases']['build-cache-probe']=dict(build=compiled,scope=scope('build-cache-probe',project),generated=generated_inventory('build-cache-probe',project),sourceCut=cut('build-cache-probe-cut',project))
   summary['ok']=compiled
   return
  if a.scenario=='cache-durability':
   calibration_root=root/'cache-calibration'
   result=subprocess.run(['node',str(Path(__file__).with_name('calibrate-cache.cjs')),str(project),str(a.reference),str(calibration_root)],capture_output=True)
   (e/'cache-calibration.stdout.json').write_bytes(result.stdout);(e/'cache-calibration.stderr.log').write_bytes(result.stderr)
   if result.returncode:
    if calibration_root.exists():shutil.copytree(calibration_root,e/'failed-cache-calibration')
    raise RuntimeError('Harness cache calibration failed; receipts retained')
   calibration=json.loads((calibration_root/'summary.json').read_text())['receipts']
   for variant in calibration:
    for stage in (1,2):
     source=calibration_root/(variant+'-stage-'+str(stage)+'.json')
     target=e/(variant+'-oracle.stdout.json' if stage==2 else 'calibration-stage1-'+variant+'.json')
     shutil.copy2(source,target);shutil.copy2(calibration_root/(variant+'-stage-'+str(stage)+'.stderr'),Path(str(target)+'.stderr'))
   reference=json.loads((e/'reference-oracle.stdout.json').read_text())
   assert set(reference['checks'])==set(seed['acceptanceChecks']['2'])
   summary['calibration']={variant+'MatchesContract':True for variant in calibration}
  elif a.scenario in ('debounce','image-url'):
   calibration_root=root/'utility-calibration'
   command=['node',str(Path(__file__).with_name('calibrate-utilities.cjs')),str(project),str(a.reference),str(calibration_root),a.scenario]
   result=subprocess.run(command,capture_output=True)
   (e/'utility-calibration.stdout.json').write_bytes(result.stdout);(e/'utility-calibration.stderr.log').write_bytes(result.stderr)
   if result.returncode:
    if calibration_root.exists():shutil.copytree(calibration_root,e/'failed-utility-calibration')
    raise RuntimeError('Harness utility calibration failed; complete receipts retained')
   calibration=json.loads((calibration_root/'summary.json').read_text())['cases'][a.scenario]
   for variant in calibration['variants']:
    for stage in (1,2):
     source=calibration_root/a.scenario/(variant+'-stage-'+str(stage)+'.json')
     target=e/(variant+'-oracle.stdout.json' if stage==2 else 'calibration-stage1-'+variant+'.json')
     shutil.copy2(source,target);shutil.copy2(Path(str(source)+'.stderr'),Path(str(target)+'.stderr'))
   reference=json.loads((e/'reference-oracle.stdout.json').read_text())
   if seed.get('acceptanceChecks'):assert set(reference['checks'])==set(seed['acceptanceChecks']['2'])
   summary['calibration']={variant+'MatchesContract':True for variant in calibration['variants']}
  else:
   baseline=oracle('baseline',project,2);reference=oracle('reference',a.reference,2)
   if seed.get('acceptanceChecks'):assert set(reference['checks'])==set(seed['acceptanceChecks']['2'])
   wrong=root/'wrong';shutil.copytree(a.reference/'common',wrong/'common');shutil.copytree(a.reference/'features',wrong/'features')
   file=wrong/paths[0]
   if a.scenario=='navigation':file.write_text(file.read_text().replace('this.pathStack.replacePath','this.pathStack.pushPath'))
   elif a.scenario=='feedback':file.write_text(file.read_text().replace('this.submitError = err.message;', 'this.submitError = err.message; this.resetAllStatus();'))
   else:file.write_text(file.read_text().replace('clearTimeout(this.delayTimer);', 'void this.delayTimer;'))
   negative=oracle({'feedback':'wrong-reset','loading':'wrong-cancel','navigation':'wrong-stack','debounce':'wrong-boundary','image-url':'wrong-protocol'}[a.scenario],wrong,2)
   assert not any(result.get('error') for result in (baseline,reference,negative)), 'Calibration infrastructure error is not a negative behavior verdict'
   summary['calibration']=dict(baselineFails=not baseline['pass'],referencePasses=reference['pass'],wrongOutcomeFails=not negative['pass'])
   if a.scenario=='loading':
    wrong_fallback=root/'wrong-fallback';shutil.copytree(a.reference/'common',wrong_fallback/'common');file=wrong_fallback/paths[1];file.write_text(file.read_text().replace('    return this.sm;\n  }','    return this.lg;\n  }'));summary['calibration']['wrongFallbackFails']=not oracle('wrong-fallback',wrong_fallback,2)['pass']
   if a.scenario=='feedback':
    duplicate=root/'wrong-duplicate';shutil.copytree(a.reference/'common',duplicate/'common');file=duplicate/paths[0];file.write_text(file.read_text().replace('this.submitting || !this.feedbackData.canSubmit','!this.feedbackData.canSubmit'));summary['calibration']['wrongDuplicateFails']=not oracle('wrong-duplicate',duplicate,2)['pass']
    wrong_initial=root/'wrong-initial';shutil.copytree(a.reference/'common',wrong_initial/'common');file=wrong_initial/paths[0];file.write_text(file.read_text().replace('@State submitting: boolean = false','@State submitting: boolean = true'));summary['calibration']['wrongInitializerFails']=not oracle('wrong-initial',wrong_initial,2)['pass']
   assert all(summary['calibration'].values())

  if not build('prepare',project,True):raise RuntimeError('Harness dependency preparation failed')
  parent=subject('parent-agent');cut('initial',project)
  try:parent.turn('turn-1',project,prompt=task_prompt(demands[0]))
  except RuntimeError as error:summary['phases']['turn-1-launch-error']=str(error)
  stage1=oracle('turn-1',project,1);built1=build('turn-1-build',project);scope1=scope('turn-1',project);cut_id=cut('turn-1-cut',project);summary['phases']['turn-1']=dict(behavior=stage1,build=built1,scope=scope1,sourceCut=cut_id)
  # Restore source from the operator cut onto original code; no reference fixes.
  branch=root/'fork-workspace';shutil.copytree(project,branch,ignore=shutil.ignore_patterns('oh_modules','node_modules','build','.hvigor','.native-build','.native-dependencies'))
  assert cut('fork-input',branch)==cut_id;summary['sourceForkQualified']=True
  for label,directory,participant in [('parent-turn-2',project,parent),('fresh-fork-turn-2',branch,None)]:
   if participant is None:fork=subject('fork-agent');participant=fork
   if directory==branch and not build('fork-prepare',directory,True):raise RuntimeError('Harness fork dependency preparation failed')
   try:participant.turn(label,directory,prompt=task_prompt(demands[1]))
   except RuntimeError as error:summary['phases'][label+'-launch-error']=str(error)
   result=oracle(label,directory,2);compiled=build(label+'-build',directory);scope_result=scope(label,directory);summary['phases'][label]=dict(behavior=result,build=compiled,scope=scope_result,sourceCut=cut(label+'-cut',directory))
  summary['subjectTaskSucceeded']=all(summary['phases'][x]['behavior']['pass'] and summary['phases'][x]['build'] for x in ['turn-1','parent-turn-2','fresh-fork-turn-2']);summary['ok']=True
 finally:
  if parent:parent.close()
  if fork:fork.close()
  dump(e/'summary.json',summary)
if __name__=='__main__':main()
