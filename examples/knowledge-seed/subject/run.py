"""Real staged navigation assessment, with explicit source-only fresh-Agent fork."""
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'real-code-agent'))
from participant import Participant
PIN='7aa95cac4eca15e39fc6638cdf1de7db6fb70ad6'
PATHS=['common/src/main/ets/routermanager/PageContext.ets','common/src/main/ets/model/PageEnum.ets','common/src/main/ets/util/Logger.ets','features/devpractices/src/main/ets/view/PracticeHomeView.ets']
DEMANDS=[
 'Expose boolean success/failure outcomes for PageContext navigation operations, including its interface. Preserve stack ownership, push/replace/pop/clear semantics, parameters, animation defaults and error logging. Keep valid ArkTS.',
 'Preserve all previous navigation behavior. In PracticeHomeView use @State navigationFailed: boolean = false; aboutToAppear must set it from the actual replacePage failure outcome and clear it on success. Preserve caller parameters and false animation. Do not install dependencies or change build configuration.']
def dump(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--install-root',type=Path,required=True);p.add_argument('--pi-runtime',type=Path,required=True);p.add_argument('--image',required=True);a=p.parse_args()
 root=a.root.resolve();root.mkdir();e=root/'evidence';e.mkdir();project=root/'workspace'
 subprocess.run(['git','clone','--shared',str(a.source.resolve()),str(project)],check=True,capture_output=True)
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=project,text=True).strip()==PIN
 lock=json.loads((a.install_root/'downloads/environment-lock.json').read_text());dump(e/'environment-lock.json',lock)
 seed=json.loads(next(line for line in (Path(__file__).resolve().parents[1]/'seeds/harmony-code-workshop/evaluation_cases.jsonl').read_text().splitlines() if json.loads(line)['id']=='case-navigation-subject-v1'));assert seed['demands']==DEMANDS
 dump(e/'frozen-task.json',seed)
 summary=dict(schema='agentlab.navigation_subject.v1',sourceRevision=PIN,demands=DEMANDS,sourceForkQualified=False,formalSessionFSForkQualified=False,uiDeviceQualified=False,phases={},ok=False,subjectTaskSucceeded=False)
 def oracle(label,directory,stage):
  command=['node',str(Path(__file__).with_name('navigation.cjs')),str(directory),str(stage)]
  r=subprocess.run(command,capture_output=True);(e/(label+'-oracle.stdout.json')).write_bytes(r.stdout);(e/(label+'-oracle.stderr.log')).write_bytes(r.stderr)
  if r.returncode:raise RuntimeError('Harness oracle infrastructure error')
  return json.loads(r.stdout)
 def cut(label,directory):
  out=e/label;out.mkdir();rows=[]
  for name in PATHS:
   raw=(directory/name).read_bytes();target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);rows.append(dict(path=name,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
  identity=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest();dump(out/'source-cut.json',dict(kind='source-only-cut',id=identity,files=rows));return identity
 sdk=next(x for x in lock['components'] if x['slot']=='harmony-cli');kit=next(x for x in lock['components'] if x['slot']=='harmony-build-kit')
 base=['docker','run','--rm','--network=none','--mount',f'type=volume,src={sdk["volume"]},dst=/toolchains/harmony,readonly','--mount',f'type=volume,src={kit["volume"]},dst=/toolchains/harmony-build-kit,readonly','--mount',f'type=bind,src={root},dst=/case','--env','HARMONY_TOOLCHAIN_ROOT=/toolchains/harmony','--env','HARMONY_BUILD_CACHE=/runtime/toolchain-cache/subject','--entrypoint','/usr/bin/python3',lock['images'][0]['reference'],'/toolchains/harmony-build-kit/bin/harmony']
 def build(label,directory,prepare=False):
  command=[x for x in base if not (prepare and x=='--network=none')]+['prepare-deps' if prepare else 'build','--project','/case/'+directory.name]
  if not prepare:command+=['--module','phone','--offline']
  dump(e/(label+'-command.json'),command);r=subprocess.run(command,capture_output=True,timeout=660 if prepare else 240);(e/(label+'-stdout.log')).write_bytes(r.stdout);(e/(label+'-stderr.log')).write_bytes(r.stderr)
  reports=directory/('.native-dependencies' if prepare else '.native-build')
  if reports.exists():shutil.copytree(reports,e/label)
  if r.returncode==0 and not prepare:
   report=json.loads((reports/'result.json').read_text());out=root/'full-hap';out.mkdir(exist_ok=True)
   for item in report['artifacts']:
    hap=directory/item['path'];assert hashlib.sha256(hap.read_bytes()).hexdigest()==item['sha256']
    name=label+'-'+hap.name;shutil.copy2(hap,out/name)
    manifest=e/'binary-manifest.json';rows=json.loads(manifest.read_text()) if manifest.exists() else []
    rows.append(dict(label=label,filename=name,sha256=item['sha256'],bytes=item['bytes'],module=item['module']));dump(manifest,rows)
  return r.returncode==0
 def subject(name):
  pe=e/name;pe.mkdir();runtime=root/(name+'-runtime');runtime.mkdir();session=runtime/'session';session.mkdir();wrapper=runtime/'container-pi.py';shutil.copy2(Path(__file__).with_name('container-pi.py'),wrapper)
  dump(runtime/'container-launch.json',dict(runtime=str(a.pi_runtime.resolve()),session=str(session),image=a.image))
  return Participant(pe,runtime/'state',wrapper,os.environ['AGENTLAB_LM_GATEWAY_URL'],os.environ.get('AGENTLAB_MODEL','glm-5.3-flash'))
 parent=None;fork=None
 try:
  baseline=oracle('baseline',project,2);reference=oracle('reference',a.reference,2)
  wrong=root/'wrong';shutil.copytree(a.reference/'common',wrong/'common');shutil.copytree(a.reference/'features/devpractices',wrong/'features/devpractices')
  file=wrong/PATHS[0];file.write_text(file.read_text().replace('this.pathStack.replacePath','this.pathStack.pushPath'));negative=oracle('wrong-stack',wrong,2)
  summary['calibration']=dict(baselineFails=not baseline['pass'],referencePasses=reference['pass'],wrongStackFails=not negative['pass']);assert all(summary['calibration'].values())
  if not build('prepare',project,True):raise RuntimeError('Harness dependency preparation failed')
  parent=subject('parent-agent');cut('initial',project)
  try:parent.turn('turn-1',project,prompt=DEMANDS[0])
  except RuntimeError as error:summary['phases']['turn-1-launch-error']=str(error)
  stage1=oracle('turn-1',project,1);built1=build('turn-1-build',project);cut_id=cut('turn-1-cut',project);summary['phases']['turn-1']=dict(behavior=stage1,build=built1,sourceCut=cut_id)
  # Restore source from the operator cut onto original code; no reference fixes.
  branch=root/'fork-workspace';shutil.copytree(project,branch,ignore=shutil.ignore_patterns('oh_modules','node_modules','build','.hvigor','.git','.native-build','.native-dependencies'))
  assert cut('fork-input',branch)==cut_id;summary['sourceForkQualified']=True
  for label,directory,participant in [('parent-turn-2',project,parent),('fresh-fork-turn-2',branch,None)]:
   if participant is None:fork=subject('fork-agent');participant=fork
   if directory==branch and not build('fork-prepare',directory,True):raise RuntimeError('Harness fork dependency preparation failed')
   try:participant.turn(label,directory,prompt=DEMANDS[1])
   except RuntimeError as error:summary['phases'][label+'-launch-error']=str(error)
   result=oracle(label,directory,2);compiled=build(label+'-build',directory);summary['phases'][label]=dict(behavior=result,build=compiled,sourceCut=cut(label+'-cut',directory))
  summary['subjectTaskSucceeded']=all(summary['phases'][x]['behavior']['pass'] and summary['phases'][x]['build'] for x in ['turn-1','parent-turn-2','fresh-fork-turn-2']);summary['ok']=True
 finally:
  if parent:parent.close()
  if fork:fork.close()
  dump(e/'summary.json',summary)
if __name__=='__main__':main()
