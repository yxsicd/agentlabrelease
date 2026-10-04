use std::{path::PathBuf, process::Command};

#[test]
fn reviewed_knowledge_transport_enforces_single_cas_and_complete_serial_pages() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let code = r#"
import importlib.util,json,os,tempfile,threading
from pathlib import Path
spec=importlib.util.spec_from_file_location('transport',os.environ['TRANSPORT'])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
old,new='a'*40,'b'*40
def client(root):
    c=module.StrictTransport.__new__(module.StrictTransport)
    c.root=root;c.current=old;c.writes=0;c.counter=0;c.lock=threading.RLock()
    c.readbacks={};c.postcommit_before=None
    c.request=dict(knowledgeRepository='any-repository')
    c.allowed={name:{name+'-id':dict(payload={'id':name+'-id'})} for name in ['maintainer_skills','program_facts','maintainer_skill_refresh_rounds']}
    return c
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    def transaction(c):return dict(repo='any-repository',expected_revision=old,topic_id='main',tables=[dict(path=k,operations=[dict(op='insert',key=i,row=r) for i,r in v.items()]) for k,v in c.allowed.items()])
    for mode in ['success','uncertain','conflict','same-revision','update','bootstrap','duplicate','drift']:
        directory=root/mode;directory.mkdir();c=client(directory);calls=[]
        def one(*args):
            calls.append(args)
            if mode=='uncertain':raise RuntimeError('unknown transport outcome')
            return dict(previous_revision=old,revision=old if mode=='same-revision' else new,outcome='applied',conflicts=['conflict'] if mode=='conflict' else [])
        c.one=one;t=transaction(c)
        if mode=='update':t['tables'][0]['operations'][0]['op']='update'
        if mode=='bootstrap':t['tables']=t['tables'][:1]
        if mode=='duplicate':t['tables'].append(t['tables'][0])
        if mode=='drift':t['expected_revision']=new
        try:c.call('skill_run_write','table.author','worktree_table_batch_transaction',t)
        except (ValueError,RuntimeError):assert mode!='success'
        else:assert mode=='success' and c.current==new
        assert len(calls)==(1 if mode in ['success','uncertain','conflict','same-revision'] else 0)
        if calls:
            assert c.writes==1 and (directory/'transaction-intent.json').exists()
            try:c.call('skill_run_write','table.author','worktree_table_batch_transaction',transaction(c))
            except ValueError:pass
            else:raise AssertionError('second write allowed')
            assert len(calls)==1
    for mode in ['complete','duplicate','revision','truncated','budget']:
        directory=root/('pages-'+mode);directory.mkdir();c=client(directory);offsets=[]
        def one(runner,skill,operation,args):
            c.counter+=1;offset=args['offset'];offsets.append(offset)
            total=1001 if mode=='budget' else 101
            rows=[dict(key=str(i),row={}) for i in range(offset,min(offset+50,total))]
            if mode=='duplicate' and offset==100:rows[0]['key']='0'
            return dict(revision=new if mode=='revision' else old,dirty=False,offset=offset,
                returned_count=len(rows),matched_count=total,row_count=total,rows=rows,
                truncated=True if mode=='truncated' else offset+len(rows)<total)
        c.one=one
        try:result=c.call('skill_run_read','table.query','table_query',dict(repo='any-repository',path='program_facts',view=dict(revision=old)))
        except ValueError:assert mode!='complete'
        else:
            assert mode=='complete' and len(result['rows'])==101 and result['truncated'] is False
            assert offsets==[0,50,100] and result['pagedReadback'] is True
        assert c.writes==0
    for mode in ['clean','dirty']:
        directory=root/('postcommit-'+mode);directory.mkdir();c=client(directory)
        c.current=new;c.writes=1;operations=[]
        def one(runner,skill,operation,args):
            c.counter+=1;operations.append(operation)
            if operation=='table_status':return dict(revision=new,dirty=mode=='dirty')
            return dict(revision=new,dirty=False,offset=0,returned_count=0,
                matched_count=0,row_count=0,rows=[],truncated=False)
        c.one=one
        try:c.call('skill_run_read','table.query','table_query',dict(repo='any-repository',path='program_facts',view=dict(revision=new)))
        except ValueError:assert mode=='dirty' and operations==['table_status']
        else:
            assert mode=='clean' and operations==['table_status','table_query']
            assert c.postcommit_before==dict(revision=new,dirty=False)
            assert c.readbacks[(new,'program_facts')]['rows']==[]
"#;
    let output = Command::new("python3")
        .args(["-c", code])
        .env(
            "TRANSPORT",
            root.join("scripts/commit-reviewed-knowledge.py"),
        )
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
}
