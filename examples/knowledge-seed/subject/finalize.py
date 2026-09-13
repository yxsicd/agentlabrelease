"""Export one fixed-cut asset class. Knowledge and experiment exports stay separate."""
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import store
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tablegit-session'));from capture import Service

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--development',type=Path,required=True);p.add_argument('--directory',type=Path,required=True);p.add_argument('--prefix',required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--include-context-history',action='store_true');a=p.parse_args();a.root.mkdir();(a.root/'rpc').mkdir();config=json.loads(a.development.read_text());s=Service(config['url'],Path(config['authorizationFile']).read_text().strip(),a.root/'rpc');repo=config['repo'];rev=s.call('table.worktree.open',dict(repo=repo,worktree={'topic_id':None}))['revision'];manifest=json.loads((a.directory/'export.json').read_text());names=list(manifest['tables'])
 if a.include_context_history:names+=['context_heads','context_commits']
 receipt=dict(schema='agentlab.asset_exchange.v1',assetClass=manifest['assetClass'],repository=repo,revision=rev,tablePrefix=a.prefix,tables={})
 for name in names:
  rows=store.read(s,repo,rev,a.prefix+name);assert all(r['assetClass']==manifest['assetClass'] for r in rows.values());raw=''.join(json.dumps(rows[k],sort_keys=True,ensure_ascii=False,separators=(',',':'))+'\n' for k in sorted(rows)).encode();output_name='source_'+name if name in ('context_heads','context_commits') else name;(a.root/(output_name+'.jsonl')).write_bytes(raw);assert {r['id']:r for r in store.jsonl_rows(raw)}==store.read(s,repo,rev,a.prefix+name);definition=s.call('table.query',dict(repo=repo,view={'kind':'committed','revision':rev},path=a.prefix+name,offset=0,limit=1))['definition'];receipt['tables'][output_name]=dict(rowCount=len(rows),sha256=hashlib.sha256(raw).hexdigest(),definition=definition)
 (a.root/'export.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
if __name__=='__main__':main()
