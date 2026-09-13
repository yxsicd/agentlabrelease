"""Build and import one evaluation instance; never modify reusable knowledge."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
# Immutable historical archive decoder names, not current business tables.
PREFIX='flywheel/harmony-v3/'
OBS='runtime_observations'
PAYLOAD='runtime_payload_chunks'
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--development',type=Path,required=True);p.add_argument('--knowledge',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--run',required=True);p.add_argument('--normalizer',type=Path,required=True);p.add_argument('--raw-archive-uri',required=True);p.add_argument('--create-tables',action='store_true');a=p.parse_args();a.root.mkdir();output=a.root/'normalized';binary=a.normalizer.resolve()
 subprocess.run([str(binary),str(a.knowledge),str(output),a.raw_archive_uri,a.run+'='+str(a.evidence)],check=True,stdout=(a.root/'normalize.stdout').open('w'),stderr=(a.root/'normalize.stderr').open('w'))
 command=[sys.executable,str(Path(__file__).with_name('import-assets.py')),'--development',str(a.development),'--directory',str(output/'instances'/a.run),'--prefix','assets/instances/'+a.run+'/','--evidence',str(a.root/'import'),'--replay-context']
 if a.create_tables:command.append('--create-tables')
 subprocess.run(command,check=True,stdout=(a.root/'import.stdout').open('w'),stderr=(a.root/'import.stderr').open('w'))
 result=dict(ok=True,assetClass='evaluation-instance',normalizerSha256=hashlib.sha256(binary.read_bytes()).hexdigest(),knowledgeUnmodified=True,importReceipt=json.loads((a.root/'import/receipt.json').read_text()));(a.root/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
