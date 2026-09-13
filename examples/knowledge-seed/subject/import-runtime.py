"""Import the complete published runtime export into a new TableGit namespace."""
import argparse,hashlib,json,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import store
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tablegit-session'));from capture import Service
from ingest import OBS,PAYLOAD

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--development',type=Path,required=True);p.add_argument('--directory',type=Path,required=True);p.add_argument('--prefix',required=True);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--create-tables',action='store_true');a=p.parse_args();a.evidence.mkdir();config=json.loads(a.development.read_text());s=Service(config['url'],Path(config['authorizationFile']).read_text().strip(),a.evidence);repo=config['repo'];wt={'topic_id':None};rev=s.call('table.worktree.open',dict(repo=repo,worktree=wt))['revision'];receipt=json.loads((a.directory/'export.json').read_text());expected={}
 for name in (OBS,PAYLOAD):
  raw=(a.directory/(name+'.jsonl')).read_bytes();meta=receipt['tables'][name];assert hashlib.sha256(raw).hexdigest()==meta['sha256'];rows=store.jsonl_rows(raw);expected[name]={row['id']:row for row in rows};assert len(rows)==len(expected[name])==meta['rowCount']
  if a.create_tables:rev=s.call('table.create',dict(repo=repo,worktree=wt,path=a.prefix+name,expected_revision=rev,definition=meta['definition'],message='Create published runtime replay table'))['revision']
 pending=[]
 for name,rows in expected.items():
  existing=store.scan(s,repo,rev,a.prefix+name)
  for key,row in rows.items():
   old=existing.get(key)
   if old:
    assert old['row']==row,('Conflicting replay row',name,key)
    continue
   pending.append((name,dict(op='insert',operation_id=str(uuid.uuid4()),key=key,row=row)))
 for start in range(0,len(pending),32):
  grouped={}
  for name,op in pending[start:start+32]:grouped.setdefault(name,[]).append(op)
  rev=store.transact(s,repo,wt,rev,[dict(path=a.prefix+name,operations=ops) for name,ops in grouped.items()],'Import full public runtime evidence')
 for name,rows in expected.items():assert store.read(s,repo,rev,a.prefix+name)==rows
 result=dict(ok=True,revision=rev,insertedRows=len(pending),allRowsExact=True);(a.evidence/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
