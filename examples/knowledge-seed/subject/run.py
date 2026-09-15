"""Real staged navigation assessment, with explicit source-only fresh-Agent fork."""
import argparse,hashlib,json,os,shutil,subprocess,sys,time,threading,urllib.error,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'real-code-agent'))
from participant import Participant
PIN='7aa95cac4eca15e39fc6638cdf1de7db6fb70ad6'
SOURCE_REPOSITORY='https://gitcode.com/HarmonyOS_Samples/sample_in_harmonyos.git'
GENERATED_PREFIXES=('.native-build/','.native-dependencies/','.hvigor/','build/','oh_modules/','node_modules/','phone/build/')
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
def pi_session_identity(path):
 if not path or not path.is_file():return None
 try:
  with path.open(errors='replace') as f:
   for _ in range(32):
    line=f.readline()
    if not line:break
    try:value=json.loads(line)
    except ValueError:continue
    if not isinstance(value,dict):continue
    kind=str(value.get('type','')).lower()
    if kind in ('session','session_start','session_header'):
     identity=value.get('id') or value.get('sessionId')
     if isinstance(identity,str) and identity:return identity
 except OSError:return None
 return None
def workspace_reconstruction_evidence(directory,root,selected_paths,source_revision=PIN):
 tracked=subprocess.run(['git','diff','--binary',source_revision,'--'],cwd=directory,capture_output=True,check=True).stdout
 status=subprocess.run(['git','status','--porcelain=v1','--untracked-files=all'],cwd=directory,capture_output=True,check=True).stdout
 tracked_paths=subprocess.check_output(['git','diff','--name-only',source_revision,'--'],cwd=directory,text=True).splitlines()
 untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=directory,text=True).splitlines()
 changed=sorted(set(tracked_paths+untracked))
 generated=[name for name in changed if name.startswith(GENERATED_PREFIXES)]
 semantic=[name for name in changed if name not in generated]
 selected=set(selected_paths);extra=[name for name in semantic if name not in selected]
 patch=root/'workspace-tracked-delta.patch';patch.write_bytes(tracked)
 status_file=root/'workspace-status.txt';status_file.write_bytes(status)
 return dict(schema='agentlab.difficulty_workspace_reconstruction.v1',
  sourceAuthority=dict(repository=SOURCE_REPOSITORY,revision=source_revision),
  trackedDelta=dict(file=patch.name,bytes=len(tracked),sha256=hashlib.sha256(tracked).hexdigest()),
  workspaceStatus=dict(file=status_file.name,bytes=len(status),sha256=hashlib.sha256(status).hexdigest()),
  changedPaths=changed,semanticChangedPaths=semantic,generatedPaths=generated,extraSemanticPaths=extra,
  semanticRehydrationEligible=not extra,
  generatedStatePolicy='Recreate deterministic Harness/build state once before SessionFS seal; all experiment arms then CoW-fork the same sealed snapshot.',
  exactOriginalPhysicalStateCaptured=False)
def gateway_preflight(e,model,route='glm'):
 url=os.environ['AGENTLAB_LM_GATEWAY_URL'].rstrip('/')+'/v1/chat/completions'
 payload=json.dumps(dict(model=model,providerId=route,stream=False,max_completion_tokens=4,messages=[dict(role='user',content='Return exactly OK.')])).encode()
 attempts=[];ready=False
 for number,delay in enumerate((0,5,15),1):
  if delay:time.sleep(delay)
  started=time.monotonic_ns();status=None;body=b'';error=None
  request=urllib.request.Request(url,data=payload,headers={'Authorization':'Bearer '+os.environ['AGENTLAB_LM_GATEWAY_KEY'],'Content-Type':'application/json'},method='POST')
  try:
   with urllib.request.build_opener().open(request,timeout=30) as response:status=response.status;body=response.read(65536)
  except urllib.error.HTTPError as exc:
   status=exc.code;body=exc.read(65536)
  except Exception as exc:error=type(exc).__name__+': '+str(exc)
  attempts.append(dict(attempt=number,delayBeforeMs=delay*1000,status=status,durationMs=(time.monotonic_ns()-started)//1_000_000,responseBytes=len(body),responseSha256=hashlib.sha256(body).hexdigest(),responsePreview=body[:1024].decode(errors='replace'),error=error))
  if status==200:
   try:
    parsed=json.loads(body);ready=isinstance(parsed,dict) and ('choices' in parsed or 'output' in parsed)
   except Exception:ready=False
  if ready:break
 result=dict(schema='agentlab.gateway_preflight.v1',endpointPath='/v1/chat/completions',model=model,providerRoute=route,ready=ready,attempts=attempts,credentialRecorded=False,taskContentSent=False)
 dump(e/'gateway-preflight.json',result);return result
def line_count(path):
 with path.open('rb') as f:return sum(1 for _ in f)
def load_guidance(path,scenario,variant='none'):
 if not path:return None
 manifest=json.loads((path/'seed-guidance.json').read_text());assert manifest['schema']=='agentlab.seed_guidance.v1' and manifest['scenario']==scenario
 export=path/'promotion-export';skills=[json.loads(line) for line in (export/'maintainer_skills.jsonl').read_text().splitlines() if line.strip()]
 promoted=[row for row in skills if row.get('sourceLessonId')==manifest['verifiedLessonId']]
 assert len(promoted)==1
 body=promoted[0]['body']
 if variant and variant!='none':
  overlay_path=Path(__file__).with_name('guidance-variants')/scenario/(variant+'.json')
  overlay=json.loads(overlay_path.read_text());assert overlay['schema']=='agentlab.guidance_variant.v1' and overlay['scenario']==scenario and overlay['id']==variant
  assert overlay['baseCandidateDigest']==manifest['candidateDigest']
  raw=overlay['body'].encode();digest=hashlib.sha256(raw).hexdigest();assert digest==overlay['bodySha256']
  manifest=dict(manifest);manifest['guidanceVariant']=dict(id=variant,digest=digest,experimental=True,decisionSourceRunId=overlay['decisionSourceRunId'],baseCandidateDigest=overlay['baseCandidateDigest'])
  body+='\n\nExperimental Agent-selected execution guidance (not verified reusable knowledge):\n'+overlay['body']
 return dict(manifest=manifest,body=body,skillId=promoted[0]['id'])
def write_infrastructure_unavailable(e,scenario_name,guidance=None,preflight=None):
 scenario=SCENARIOS[scenario_name]
 seed=json.loads(next(line for line in (Path(__file__).resolve().parents[1]/'seeds/harmony-code-workshop/evaluation_cases.jsonl').read_text().split('\n') if line.strip() and json.loads(line)['id']==scenario['caseId']))
 e.mkdir(parents=True,exist_ok=True);dump(e/'frozen-task.json',seed)
 if preflight is not None:dump(e/'gateway-preflight.json',preflight)
 manifest=(guidance['manifest'] if guidance else None)
 if manifest:dump(e/'seed-guidance.json',manifest)
 summary=dict(schema='agentlab.'+scenario_name+'_subject.v1',taskId=scenario['caseId'],assessmentScope=scenario['scope'],sourceRevision=PIN,demands=scenario['demands'],sourceForkQualified=False,formalSessionFSForkQualified=False,uiDeviceQualified=False,phases={},timing=dict(builds=[],participantEdits=[]),ok=True,subjectTaskSucceeded=None,assessmentStatus='infrastructure-unavailable',infrastructureAvailable=False)
 decision=dict(schema='agentlab.harness_decision_package.v1',scenario=scenario_name,taskId=scenario['caseId'],sourceRevision=PIN,assessmentStatus='infrastructure-unavailable',infrastructureAvailable=False,subjectTaskSucceeded=None,sourceForkQualified=False,seedGuidance=manifest,phaseVerdicts=[],participantProcess=[],launchErrors=[dict(phase='gateway-preflight',error='Model gateway readiness failed before assessed dispatch')],buildTiming=dict(firstCompileStartMs=None,builds=[]),evidenceCost=dict(successfulHapCount=0,successfulHapBytes=0,retainedHapCount=0,retainedHapBytes=0,retentionPolicy='fast-manifest-only'),automaticAttributionCandidates=[dict(kind='transport-gateway-unavailable',strength='verified-preflight',evidence=['gateway-preflight'],claim='The configured model route did not become ready after bounded preflight retries; no assessed Participant turn was dispatched.')],uncertainties=['No Participant/model-quality conclusion is permitted because assessed dispatch did not begin.'],agentDecisionRequired=True,allowedDecisions=['rerun-control','rerun-guided','design-next-experiment'],harnessPolicy='Collect, verify, compare and propose evidence-linked candidates; never choose promotion or seed adoption automatically.')
 dump(e/'summary.json',summary);dump(e/'decision-package.json',decision);return decision
def main():
 p=argparse.ArgumentParser();p.add_argument('--scenario',choices=SCENARIOS,default='navigation');p.add_argument('--source',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--install-root',type=Path,required=True);p.add_argument('--pi-runtime',type=Path,required=True);p.add_argument('--image',required=True);p.add_argument('--build-cache-probe-only',action='store_true');p.add_argument('--retain-hap-bytes',action='store_true');p.add_argument('--guidance',type=Path);p.add_argument('--guidance-variant',default='none');p.add_argument('--compiler-feedback-only',action='store_true');p.add_argument('--timeout-feedback-only',action='store_true');p.add_argument('--resume-difficulty-checkpoint',type=Path);a=p.parse_args();assert not (a.compiler_feedback_only and a.timeout_feedback_only),'intervention modes are mutually exclusive';assert not a.resume_difficulty_checkpoint or (a.compiler_feedback_only != a.timeout_feedback_only),'resume checkpoint requires exactly one focused intervention mode'
 scenario=SCENARIOS[a.scenario];paths=scenario['paths'];demands=scenario['demands']
 experiment_started=time.monotonic_ns()
 root=a.root.resolve();root.mkdir();e=root/'evidence';e.mkdir();project=root/'workspace'
 subprocess.run(['git','clone','--no-hardlinks',str(a.source.resolve()),str(project)],check=True,capture_output=True)
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=project,text=True).strip()==PIN
 resume_manifest=None;resume_session=None;resume_patch=None;resume_oracle_stage=1;resume_demand_index=0;resume_lifecycle=None;resume_edit=None
 if a.resume_difficulty_checkpoint:
  resume_root=a.resume_difficulty_checkpoint.resolve();resume_manifest=json.loads((resume_root/'checkpoint.json').read_text())
  assert resume_manifest['schema']=='agentlab.difficulty_checkpoint_candidate.v1'
  assert resume_manifest['sourceRevision']==PIN and resume_manifest['taskId']==scenario['caseId']
  expected=(True,False) if a.compiler_feedback_only else (False,True)
  assert (resume_manifest['behaviorPass'],resume_manifest['buildPass'])==expected
  if a.timeout_feedback_only:
   resume_lifecycle=json.loads((resume_root/'source-lifecycle.json').read_text())
   resume_edit=json.loads((resume_root/'source-edit-timing.json').read_text())
   assert resume_lifecycle.get('timedOut') is True and resume_edit.get('firstSourceMutationMs') is None
  if resume_manifest['phase'] in ('parent-turn-2','fresh-fork-turn-2'):
   resume_oracle_stage=2;resume_demand_index=1
  resume_patch=resume_root/'workspace-tracked-delta.patch';assert resume_patch.is_file()
  tracked=resume_manifest.get('reconstruction',{}).get('trackedDelta',{})
  if tracked.get('sha256'):assert sha256_file(resume_patch)==tracked['sha256']
  resume_session=resume_root/resume_manifest['nativeSession']['file'];assert resume_session.is_file()
  assert sha256_file(resume_session)==resume_manifest['nativeSession']['sha256']
 lock=json.loads((a.install_root/'downloads/environment-lock.json').read_text());dump(e/'environment-lock.json',lock)
 seed=json.loads(next(line for line in (Path(__file__).resolve().parents[1]/'seeds/harmony-code-workshop/evaluation_cases.jsonl').read_text().split('\n') if line.strip() and json.loads(line)['id']==scenario['caseId']));assert seed['demands']==demands
 dump(e/'frozen-task.json',seed)
 guidance=load_guidance(a.guidance,a.scenario,a.guidance_variant)
 if guidance:dump(e/'seed-guidance.json',guidance['manifest'])
 if seed.get('oracleDigest'):assert hashlib.sha256(Path(__file__).with_name(scenario['oracle']).read_bytes()).hexdigest()==seed['oracleDigest']
 summary=dict(schema='agentlab.'+a.scenario+'_subject.v1',taskId=scenario['caseId'],assessmentScope=scenario['scope'],sourceRevision=PIN,demands=demands,sourceForkQualified=False,formalSessionFSForkQualified=False,uiDeviceQualified=False,phases={},timing=dict(builds=[],participantEdits=[]),ok=False,subjectTaskSucceeded=False)
 receipt=os.environ.get('AGENTLAB_GATEWAY_PREFLIGHT_RECEIPT')
 if receipt and Path(receipt).is_file():
  preflight=json.loads(Path(receipt).read_text());dump(e/'gateway-preflight.json',preflight)
 else:preflight=gateway_preflight(e,os.environ.get('AGENTLAB_MODEL','glm-5.3-flash'))
 if not preflight['ready']:
  write_infrastructure_unavailable(e,a.scenario,guidance,preflight);return
 summary['assessmentStatus']='assessed';summary['infrastructureAvailable']=True
 def oracle(label,directory,stage):
  for variable in ('AGENTLAB_SOURCE_PROBE','AGENTLAB_ORACLE_TYPESCRIPT'):
   value=os.environ.get(variable);assert value and Path(value).exists(), 'Harness oracle dependency missing: '+variable
  command=['node',str(Path(__file__).with_name(scenario['oracle'])),str(directory),str(stage)]
  r=subprocess.run(command,capture_output=True);(e/(label+'-oracle.stdout.json')).write_bytes(r.stdout);(e/(label+'-oracle.stderr.log')).write_bytes(r.stderr)
  if r.returncode:
   if a.scenario!='cache-durability':raise RuntimeError('Harness oracle infrastructure error')
   result={'stage':stage,'schema':'agentlab.cache_durability_probe.v1','pass':False,'checks':{},'error':r.stderr.decode(errors='replace').strip() or 'cache oracle exited non-zero','oracleProcessExitCode':r.returncode,'errorClassification':'submitted-source-evaluation-error','referenceTransformsApplied':False,'actualModulesExecuted':0,'qualification':dict(candidateOnly=True,phoneBuild=False,pageUI=False,actualAgent=False)}
   dump(e/(label+'-oracle.stdout.json'),result);return result
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
  raw=sorted(set(tracked+untracked))
  generated=[name for name in raw if name.startswith(GENERATED_PREFIXES)];changed=[name for name in raw if name not in generated]
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
  prompt=demand+'\n\nAssessed edit boundary (frozen task paths):\n'+allowed+'\nYou may read other files for context, but do not modify files outside this list. If you believe another file must change, leave it unchanged and report the reason instead. Out-of-scope writes are independently measured.'
  if guidance:prompt+='\n\nVerified prior-run engineering guidance (not task answer; frozen demands/oracle are unchanged):\n'+guidance['body']
  return prompt
 def feedback_prompt(stage,compiled):
  notes=[]
  if not stage.get('pass'):
   failed=[name for name,value in stage.get('checks',{}).items() if value is False]
   if failed:notes.append('Behavior checks still failing: '+', '.join(failed[:8]))
   if stage.get('error'):notes.append('Behavior evaluation error: '+str(stage['error'])[:1200])
  if not compiled:
   path=e/'turn-1-build-stderr.log'
   if path.is_file():
    lines=[line.strip() for line in path.read_text(errors='replace').splitlines() if (' ERROR:' in line or 'Error Message:' in line)]
    if lines:notes.append('Compiler evidence from the previous phase:\n'+'\n'.join(lines[-10:])[:2200])
  if not notes:return None
  return ('Harness feedback from the previous assessed phase. This is observed verifier/compiler evidence, not a reference answer. '
          'Repair the current source against this evidence before broadening scope.\n'+'\n'.join(notes))
 def monitored_turn(label,directory,participant,prompt,reasoning_effort=None):
  def snapshot():
   result={}
   for name in paths:
    path=directory/name
    result[name]=sha256_file(path) if path.is_file() else None
   return result
  baseline=snapshot();stop=threading.Event();started=time.monotonic_ns();record=dict(phase=label,firstSourceMutationMs=None,firstChangedPaths=[],samplingIntervalMs=250,detection='none')
  def watch():
   while not stop.wait(0.25):
    current=snapshot();changed=[name for name in paths if current[name]!=baseline[name]]
    if changed:
     record.update(firstSourceMutationMs=(time.monotonic_ns()-started)//1_000_000,firstChangedPaths=changed,detection='sampled');return
  thread=threading.Thread(target=watch,daemon=True);thread.start()
  try:participant.turn(label,directory,prompt=prompt,reasoning_effort=reasoning_effort)
  finally:
   stop.set();thread.join(timeout=1)
   if record['firstSourceMutationMs'] is None:
    current=snapshot();changed=[name for name in paths if current[name]!=baseline[name]]
    if changed:record.update(firstSourceMutationMs=(time.monotonic_ns()-started)//1_000_000,firstChangedPaths=changed,detection='post-turn')
   summary['timing']['participantEdits'].append(record);dump(e/(label+'-edit-timing.json'),record)
 sdk=next(x for x in lock['components'] if x['slot']=='harmony-cli');kit=next(x for x in lock['components'] if x['slot']=='harmony-build-kit')
 build_cache=Path(os.environ['AGENTLAB_HARMONY_BUILD_CACHE_HOST']).resolve();build_cache.mkdir(parents=True,exist_ok=True)
 fast_cli_raw=os.environ.get('AGENTLAB_FAST_HARMONY_ROOT');fast_kit_raw=os.environ.get('AGENTLAB_FAST_BUILD_KIT_ROOT')
 fast_cli=Path(fast_cli_raw).resolve() if fast_cli_raw and Path(fast_cli_raw).is_dir() else None
 fast_kit=Path(fast_kit_raw).resolve() if fast_kit_raw and Path(fast_kit_raw).is_dir() else None
 if bool(fast_cli)!=bool(fast_kit):raise RuntimeError('FAST_TOOLCHAIN_PAIR_REQUIRED')
 toolchain_mounts=(['--mount',f'type=bind,src={fast_cli},dst=/toolchains/harmony,readonly','--mount',f'type=bind,src={fast_kit},dst=/toolchains/harmony-build-kit,readonly'] if fast_cli else ['--mount',f'type=volume,src={sdk["volume"]},dst=/toolchains/harmony,readonly','--mount',f'type=volume,src={kit["volume"]},dst=/toolchains/harmony-build-kit,readonly'])
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
  effort=os.environ.get('AGENTLAB_REASONING_EFFORT','default')
  participant=Participant(pe,runtime/'state',wrapper,os.environ['AGENTLAB_LM_GATEWAY_URL'],os.environ.get('AGENTLAB_MODEL','glm-5.3-flash'),reasoning_effort=effort)
  participant.native_session_file=session/'session.jsonl'
  return participant
 def capture_difficulty_checkpoint(phase,directory,participant,behavior,compiled,source_cut):
  session=getattr(participant,'native_session_file',None)
  if not session or not session.is_file():return None
  root=e/'difficulty-checkpoints'/phase;root.mkdir(parents=True,exist_ok=True)
  target=root/'pi-session.jsonl';shutil.copy2(session,target)
  reconstruction=workspace_reconstruction_evidence(directory,root,paths,PIN)
  source=root/'source';source.mkdir()
  files=[]
  for name in paths:
   origin=directory/name
   if not origin.is_file():files.append(dict(path=name,absent=True));continue
   raw=origin.read_bytes();out=source/name;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(raw)
   files.append(dict(path=name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
  manifest=dict(schema='agentlab.difficulty_checkpoint_candidate.v1',phase=phase,sourceRevision=PIN,sourceCut=source_cut,
   taskId=scenario['caseId'],behaviorPass=behavior.get('pass'),buildPass=compiled,
   nativeSession=dict(agent='pi',packageVersion='0.73.1',file='pi-session.jsonl',bytes=target.stat().st_size,sha256=sha256_file(target),threadId=pi_session_identity(target)),
   selectedSourceFiles=files,reconstruction=reconstruction,
   semanticRehydrationEligible=reconstruction['semanticRehydrationEligible'],formalSessionFsSnapshot=False,readyForControlledFork=False,
   promotionRequirement='Rehydrate exact Git revision + full tracked delta + native session, recreate declared immutable/generated runtime state once, then seal/verify one SessionFS snapshot before any model/parameter sweep.',
   persistedObservableState=['source-revision-authority','workspace-tracked-delta','workspace-status','selected-source','pi-native-session'],
   recreatedBeforeSeal=['readonly-participant-runtime','readonly-model-config','harmony-generated-state'],
   missingObservableState=['exact-original-physical-workspace'],
   neverPersist=['provider-hidden-state','process-memory','pid','tcp-connection'],agentDecisionRequired=True)
  dump(root/'checkpoint.json',manifest);return str((root/'checkpoint.json').relative_to(e))
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

  if resume_manifest:
   if resume_patch.stat().st_size:
    subprocess.run(['git','apply','--check',str(resume_patch)],cwd=project,check=True,capture_output=True)
    subprocess.run(['git','apply',str(resume_patch)],cwd=project,check=True,capture_output=True)
   for row in resume_manifest.get('selectedSourceFiles',[]):
    path=project/row['path']
    if row.get('absent'):assert not path.exists()
    else:assert path.is_file() and sha256_file(path)==row['sha256']
  if not build('prepare',project,True):raise RuntimeError('Harness dependency preparation failed')
  parent=subject('parent-agent')
  if resume_manifest:
   shutil.copy2(resume_session,parent.native_session_file)
   summary['resumeDifficultyCheckpoint']=dict(
   mode='semantic-rehydration-exact-native-session',
    sourceRunId=os.environ.get('AGENTLAB_RESUME_CHECKPOINT_RUN_ID'),
    sourcePhase=resume_manifest['phase'],sourceCut=resume_manifest['sourceCut'],
    inputSessionSha256=resume_manifest['nativeSession']['sha256'],
    nativeThreadId=resume_manifest['nativeSession'].get('threadId'),
    oracleStage=resume_oracle_stage,taskDemandIndex=resume_demand_index,
    sourceTimedOut=(resume_lifecycle.get('timedOut') if resume_lifecycle else None),
    sourceFirstMutationMs=(resume_edit.get('firstSourceMutationMs') if resume_edit else None),
    formalSessionFSForkQualified=False)
  cut('initial',project)
  if not resume_manifest:
   try:monitored_turn('turn-1',project,parent,task_prompt(demands[0]))
   except RuntimeError as error:summary['phases']['turn-1-launch-error']=str(error)
  stage1=oracle('turn-1',project,resume_oracle_stage if resume_manifest else 1);built1=build('turn-1-build',project);scope1=scope('turn-1',project);cut_id=cut('turn-1-cut',project);summary['phases']['turn-1']=dict(behavior=stage1,build=built1,scope=scope1,sourceCut=cut_id)
  if resume_manifest:
   if not (stage1.get('pass') is resume_manifest['behaviorPass'] and built1 is resume_manifest['buildPass'] and cut_id==resume_manifest['sourceCut']):
    raise RuntimeError('rehydrated difficulty checkpoint failed source/behavior/build equivalence gate')
   summary['resumeDifficultyCheckpoint']['requalified']=True
  summary['phases']['turn-1']['difficultyCheckpointCandidate']=capture_difficulty_checkpoint('turn-1',project,parent,stage1,built1,cut_id)
  turn2_feedback=feedback_prompt(stage1,built1)
  if a.timeout_feedback_only:
   lifecycle=resume_lifecycle if resume_manifest else json.loads((e/'parent-agent/turn-1-lifecycle.json').read_text())
   edit=resume_edit if resume_manifest else json.loads((e/'turn-1-edit-timing.json').read_text())
   if not (stage1.get('pass') is False and built1 is True and lifecycle.get('timedOut') is True and edit.get('firstSourceMutationMs') is None):
    raise RuntimeError('timeout-feedback-only requires behavior FAIL/build PASS and timeout-before-source-mutation')
   before_requests=parent.requests;repair_started=time.monotonic_ns()
   feedback=('Harness timing feedback from the previous assessed phase: the prior attempt reached the 420000 ms participant budget without any source mutation. '
             'Continue the exact same task. Prioritize a minimal source change within the frozen edit boundary before further broad exploration. '
             'This is observed timing evidence, not a reference implementation or code answer.')
   repair_prompt=task_prompt(demands[resume_demand_index if resume_manifest else 0])+'\n\n'+feedback
   try:monitored_turn('timeout-feedback-repair',project,parent,repair_prompt,reasoning_effort=None)
   except RuntimeError as error:summary['phases']['timeout-feedback-repair-launch-error']=str(error)
   repair_behavior=oracle('timeout-feedback-repair',project,resume_oracle_stage if resume_manifest else 1);repair_build=build('timeout-feedback-repair-build',project);repair_scope=scope('timeout-feedback-repair',project);repair_cut=cut('timeout-feedback-repair-cut',project)
   repair_duration=(time.monotonic_ns()-repair_started)//1_000_000;repair_requests=parent.requests-before_requests
   summary['phases']['timeout-feedback-repair']=dict(behavior=repair_behavior,build=repair_build,scope=repair_scope,sourceCut=repair_cut,repairLatencyMs=repair_duration,gatewayRequests=repair_requests,intervention='timeout-evidence-only',taskDemand=('turn-'+str((resume_demand_index if resume_manifest else 0)+1)),oracleStage=(resume_oracle_stage if resume_manifest else 1))
   summary['phases']['timeout-feedback-repair']['difficultyCheckpointCandidate']=capture_difficulty_checkpoint('timeout-feedback-repair',project,parent,repair_behavior,repair_build,repair_cut)
   turn1_checkpoint=json.loads((e/'difficulty-checkpoints/turn-1/checkpoint.json').read_text());repair_checkpoint=json.loads((e/'difficulty-checkpoints/timeout-feedback-repair/checkpoint.json').read_text())
   input_session_sha=turn1_checkpoint['nativeSession']['sha256'];output_session_sha=repair_checkpoint['nativeSession']['sha256']
   if output_session_sha==input_session_sha:raise RuntimeError('timeout-feedback-only native session did not advance')
   summary['timeoutFeedbackOnly']=dict(enabled=True,inputPhase='turn-1',repairPhase='timeout-feedback-repair',sameNativeSession=True,sameTaskDemand=True,taskDemandIndex=(resume_demand_index if resume_manifest else 0),oracleStage=(resume_oracle_stage if resume_manifest else 1),providerReasoningEffort='default',piThinkingMode='off',gatewayRequests=repair_requests,repairLatencyMs=repair_duration,inputSessionSha256=input_session_sha,outputSessionSha256=output_session_sha,sessionAdvanced=True)
   summary['subjectTaskSucceeded']=bool(repair_behavior.get('pass') and repair_build);summary['ok']=True
   return
  if a.compiler_feedback_only:
   if not (stage1.get('pass') is True and built1 is False and turn2_feedback):
    raise RuntimeError('compiler-feedback-only requires turn-1 behavior PASS and build FAIL with concrete compiler evidence')
   before_requests=parent.requests
   repair_started=time.monotonic_ns()
   repair_prompt=task_prompt(demands[resume_demand_index if resume_manifest else 0])+'\n\n'+turn2_feedback
   try:monitored_turn('compiler-feedback-repair',project,parent,repair_prompt,reasoning_effort=None)
   except RuntimeError as error:summary['phases']['compiler-feedback-repair-launch-error']=str(error)
   repair_behavior=oracle('compiler-feedback-repair',project,resume_oracle_stage if resume_manifest else 1);repair_build=build('compiler-feedback-repair-build',project);repair_scope=scope('compiler-feedback-repair',project);repair_cut=cut('compiler-feedback-repair-cut',project)
   repair_duration=(time.monotonic_ns()-repair_started)//1_000_000
   repair_requests=parent.requests-before_requests
   summary['phases']['compiler-feedback-repair']=dict(behavior=repair_behavior,build=repair_build,scope=repair_scope,sourceCut=repair_cut,repairLatencyMs=repair_duration,gatewayRequests=repair_requests,intervention='compiler-evidence-only',taskDemand=('turn-'+str((resume_demand_index if resume_manifest else 0)+1)),oracleStage=(resume_oracle_stage if resume_manifest else 1))
   summary['phases']['compiler-feedback-repair']['difficultyCheckpointCandidate']=capture_difficulty_checkpoint('compiler-feedback-repair',project,parent,repair_behavior,repair_build,repair_cut)
   turn1_checkpoint=json.loads((e/'difficulty-checkpoints/turn-1/checkpoint.json').read_text())
   repair_checkpoint=json.loads((e/'difficulty-checkpoints/compiler-feedback-repair/checkpoint.json').read_text())
   input_session_sha=turn1_checkpoint['nativeSession']['sha256'];output_session_sha=repair_checkpoint['nativeSession']['sha256']
   if output_session_sha==input_session_sha:raise RuntimeError('compiler-feedback-only native session did not advance')
   summary['compilerFeedbackOnly']=dict(enabled=True,inputPhase='turn-1',repairPhase='compiler-feedback-repair',sameNativeSession=True,sameTaskDemand=True,taskDemandIndex=(resume_demand_index if resume_manifest else 0),oracleStage=(resume_oracle_stage if resume_manifest else 1),providerReasoningEffort='default',piThinkingMode='off',gatewayRequests=repair_requests,repairLatencyMs=repair_duration,inputSessionSha256=input_session_sha,outputSessionSha256=output_session_sha,sessionAdvanced=True)
   summary['subjectTaskSucceeded']=bool(repair_behavior.get('pass') and repair_build);summary['ok']=True
   return
  escalate=bool(turn2_feedback and os.environ.get('AGENTLAB_EVIDENCE_REASONING_ESCALATION','false')=='true')
  summary['evidenceTriggeredEscalation']=dict(triggered=escalate,reason=('turn-1-verifier-or-build-failure' if escalate else None),reasoningEffort=('high' if escalate else None),feedbackPresent=bool(turn2_feedback))
  # Restore source from the operator cut onto original code; no reference fixes.
  branch=root/'fork-workspace';shutil.copytree(project,branch,ignore=shutil.ignore_patterns('oh_modules','node_modules','build','.hvigor','.native-build','.native-dependencies'))
  assert cut('fork-input',branch)==cut_id;summary['sourceForkQualified']=True
  for label,directory,participant in [('parent-turn-2',project,parent),('fresh-fork-turn-2',branch,None)]:
   if participant is None:fork=subject('fork-agent');participant=fork
   if directory==branch and not build('fork-prepare',directory,True):raise RuntimeError('Harness fork dependency preparation failed')
   prompt=task_prompt(demands[1])
   if turn2_feedback:prompt+='\n\n'+turn2_feedback
   if escalate:prompt+='\n\nReasoning escalation: inspect the concrete evidence carefully, make the smallest compatible repair, and preserve already-passing behavior.'
   try:monitored_turn(label,directory,participant,prompt,reasoning_effort=('high' if escalate else None))
   except RuntimeError as error:summary['phases'][label+'-launch-error']=str(error)
   result=oracle(label,directory,2);compiled=build(label+'-build',directory);scope_result=scope(label,directory);phase_cut=cut(label+'-cut',directory);summary['phases'][label]=dict(behavior=result,build=compiled,scope=scope_result,sourceCut=phase_cut)
   summary['phases'][label]['difficultyCheckpointCandidate']=capture_difficulty_checkpoint(label,directory,participant,result,compiled,phase_cut)
  summary['subjectTaskSucceeded']=all(summary['phases'][x]['behavior']['pass'] and summary['phases'][x]['build'] for x in ['turn-1','parent-turn-2','fresh-fork-turn-2']);summary['ok']=True
 finally:
  if parent:parent.close()
  if fork:fork.close()
  phase_names=(['turn-1','compiler-feedback-repair'] if a.compiler_feedback_only else ['turn-1','timeout-feedback-repair'] if a.timeout_feedback_only else ['turn-1','parent-turn-2','fresh-fork-turn-2'])
  verdicts=[];launch_errors=[];scope_drift=[]
  for name in phase_names:
   phase=summary['phases'].get(name,{})
   verdicts.append(dict(phase=name,behaviorPass=phase.get('behavior',{}).get('pass'),buildPass=phase.get('build'),scopeDrift=phase.get('scope',{}).get('drift'),extraPaths=phase.get('scope',{}).get('extraPaths',[])))
   if phase.get('scope',{}).get('drift'):scope_drift.append(name)
   err=summary['phases'].get(name+'-launch-error')
   if err:launch_errors.append(dict(phase=name,error=err))
  build_rows=[x for x in summary.get('timing',{}).get('builds',[]) if not x.get('prepare')]
  candidates=[]
  if scope_drift:candidates.append(dict(kind='scope-expansion',strength='observed',evidence=scope_drift,claim='Participant changed files outside the frozen edit boundary.'))
  if any(v['behaviorPass'] is True and v['buildPass'] is False for v in verdicts):candidates.append(dict(kind='compile-regression-after-behavior-pass',strength='observed',evidence=[v['phase'] for v in verdicts if v['behaviorPass'] is True and v['buildPass'] is False],claim='Behavior oracle passed while full Harmony compilation failed.'))
  if any(v['behaviorPass'] is False and v['buildPass'] is True for v in verdicts):candidates.append(dict(kind='behavioral-incompleteness-with-compilable-patch',strength='observed',evidence=[v['phase'] for v in verdicts if v['behaviorPass'] is False and v['buildPass'] is True],claim='Submitted patch compiled but did not satisfy the frozen behavior oracle.'))
  guidance_manifest=guidance['manifest'] if guidance else None
  manifest=e/'binary-manifest.json';binaries=json.loads(manifest.read_text()) if manifest.exists() else []
  evidence_cost=dict(successfulHapCount=len(binaries),successfulHapBytes=sum(x.get('bytes',0) for x in binaries),retainedHapCount=sum(bool(x.get('retainedBytes')) for x in binaries),retainedHapBytes=sum(x.get('bytes',0) for x in binaries if x.get('retainedBytes')),retentionPolicy=('qualification-full-bytes' if a.retain_hap_bytes else 'fast-manifest-only'))
  participant_process=[]
  edit_timing={row['phase']:row for row in summary.get('timing',{}).get('participantEdits',[])}
  participant_phase_sources=([('turn-1','parent-agent'),('compiler-feedback-repair','parent-agent')] if a.compiler_feedback_only else [('turn-1','parent-agent'),('timeout-feedback-repair','parent-agent')] if a.timeout_feedback_only else [('turn-1','parent-agent'),('parent-turn-2','parent-agent'),('fresh-fork-turn-2','fork-agent')])
  for name,directory in participant_phase_sources:
   lifecycle=e/directory/(name+'-lifecycle.json')
   if lifecycle.exists():
    row=json.loads(lifecycle.read_text());edit=edit_timing.get(name,{});events=e/directory/(name+'-events.jsonl');event_bytes=events.stat().st_size if events.exists() else 0;event_lines=line_count(events) if events.exists() else 0
    retry_receipt=e/directory/(name+'-transport-retry.json');retry_count=retry_duration=retry_event_bytes=retry_event_lines=0
    if retry_receipt.exists():
     retry_count=json.loads(retry_receipt.read_text()).get('retryCount',0);retry_lifecycle=e/directory/(name+'-transport-attempt-1-lifecycle.json');retry_events=e/directory/(name+'-transport-attempt-1-events.jsonl')
     if retry_lifecycle.exists():retry_duration=json.loads(retry_lifecycle.read_text()).get('durationMs') or 0
     if retry_events.exists():retry_event_bytes=retry_events.stat().st_size;retry_event_lines=line_count(retry_events)
    participant_process.append(dict(phase=name,durationMs=row.get('durationMs'),effectiveDurationMs=(row.get('durationMs') or 0)+retry_duration,timedOut=row.get('timedOut'),exitCode=row.get('exitCode'),providerReasoningEffort=row.get('providerReasoningEffort'),completedToolCalls=row.get('completedToolCalls'),toolErrors=row.get('toolErrors'),nativeParseErrors=row.get('nativeParseErrors'),transportRetryCount=retry_count,transportRetryDurationMs=retry_duration,firstSourceMutationMs=edit.get('firstSourceMutationMs'),firstChangedPaths=edit.get('firstChangedPaths',[]),mutationDetection=edit.get('detection'),rawEventBytes=event_bytes,rawEventLines=event_lines,transportRetryRawEventBytes=retry_event_bytes,transportRetryRawEventLines=retry_event_lines,effectiveRawEventBytes=event_bytes+retry_event_bytes))
  timeout_phases=[x['phase'] for x in participant_process if x.get('timedOut')]
  transport_errors=[x for x in launch_errors if any(token in x['error'].lower() for token in ('frp','http 404','404 <!doctype','502','gateway exchange failed'))]
  other_launch_errors=[x for x in launch_errors if x not in transport_errors and x['phase'] not in timeout_phases]
  if timeout_phases:candidates.append(dict(kind='participant-budget-timeout',strength='observed',evidence=timeout_phases,claim='Participant hit the fixed execution deadline; timing/tool evidence is required before attributing the cause.'))
  if transport_errors:candidates.append(dict(kind='transport-launch-failure',strength='observed',evidence=[x['phase'] for x in transport_errors],claim='Participant launch/model exchange failed at the transport or gateway boundary before a normal assessed turn completed.'))
  if other_launch_errors:candidates.append(dict(kind='participant-launch-failure',strength='observed',evidence=[x['phase'] for x in other_launch_errors],claim='Participant did not complete normally for a non-timeout, non-transport launch reason; inspect retained events and stderr.'))
  reasoning_effort=os.environ.get('AGENTLAB_REASONING_EFFORT','default')
  decision=dict(schema='agentlab.harness_decision_package.v1',scenario=a.scenario,taskId=scenario['caseId'],sourceRevision=PIN,assessmentStatus='assessed',infrastructureAvailable=True,subjectTaskSucceeded=summary.get('subjectTaskSucceeded'),sourceForkQualified=summary.get('sourceForkQualified'),seedGuidance=guidance_manifest,reasoningPolicy=dict(piThinkingMode='off',providerReasoningEffort=(None if reasoning_effort=='default' else reasoning_effort),source='operator-owned-gateway-proxy'),evidenceTriggeredEscalation=summary.get('evidenceTriggeredEscalation'),phaseVerdicts=verdicts,participantProcess=participant_process,launchErrors=launch_errors,buildTiming=dict(firstCompileStartMs=summary.get('timing',{}).get('firstCompileStartMs'),builds=build_rows),evidenceCost=evidence_cost,automaticAttributionCandidates=candidates,uncertainties=['Participant/model latency is not inferred from timeout alone.','Runner variance may affect wall-clock timing.','Calibration proves the declared seam only; device/UI and formal SessionFS remain separate unless independently qualified.'],agentDecisionRequired=True,allowedDecisions=['adopt-guidance','reject-guidance','rerun-control','rerun-guided','modify-guidance','design-next-experiment'],harnessPolicy='Collect, verify, compare and propose evidence-linked candidates; never choose promotion or seed adoption automatically.')
  dump(e/'decision-package.json',decision)
  dump(e/'summary.json',summary)
if __name__=='__main__':main()
