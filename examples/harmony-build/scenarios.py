"""Deterministic Harmony seeds, demand deltas and independent source oracles."""
import hashlib
import json
import re

NAMES=['hello','counter','form']


def demands(name,stage):
    if name=='counter':
        return 'Keep a @State count initialized to 0 and display it. Add an Increment button that increases count by 1.' + (' Add a Reset button that sets count to 0.' if stage==2 else '')
    if name=='form':
        return 'Keep a @State name string initialized empty. Add a TextInput whose onChange updates name, and display name.' + (' Add a Clear button that empties name.' if stage==2 else '')
    return ''


def render(name,stage,marker):
    state=''
    extra=''
    if name=='counter':
        state='  @State count: number = 0;\n'
        extra="      Text(`${this.count}`)\n"
        if stage>=1: extra+="      Button('Increment').onClick(() => { this.count += 1; })\n"
        if stage>=2: extra+="      Button('Reset').onClick(() => { this.count = 0; })\n"
    if name=='form':
        state="  @State name: string = '';\n"
        extra='      Text(this.name)\n'
        if stage>=1: extra+="      TextInput({ placeholder: 'Name' }).onChange((value: string) => { this.name = value; })\n"
        if stage>=2: extra+="      Button('Clear').onClick(() => { this.name = ''; })\n"
    return '@Entry\n@Component\nstruct Index {\n'+state+'  build() {\n    Column() {\n      Text('+json.dumps(marker)+').fontSize(24)\n'+extra+'    }.width("100%").height("100%").justifyContent(FlexAlign.Center)\n  }\n}\n'


def verify(name,stage,source):
    patterns=[]
    if name=='counter':
        patterns=[r'@State\s+count',r'Text\([^)]*this\.count',r'Button\(\s*[\'\"]Increment[\'\"]\s*\)',r'this\.count\s*(\+\+|\+=\s*1|=\s*this\.count\s*\+\s*1)']
        if stage==2: patterns += [r'Button\(\s*[\'\"]Reset[\'\"]\s*\)',r'this\.count\s*=\s*0']
    if name=='form':
        patterns=[r'@State\s+name',r'Text\(\s*this\.name\s*\)',r'TextInput\(',r'\.onChange\(',r'this\.name\s*=']
        if stage==2: patterns += [r'Button\(\s*[\'\"]Clear[\'\"]\s*\)',r'this\.name\s*=\s*[\'\"]{2}']
    results=[dict(pattern=p,matched=re.search(p,source) is not None) for p in patterns]
    return dict(scenario=name,stage=stage,checks=results,passed=all(r['matched'] for r in results),scope='Source contract plus independent HAP compilation; no device interaction claim')


def manifest(name):
    if name not in NAMES: raise ValueError('unknown Harmony scenario')
    seed=render(name,0,'Native Build Verified')
    return dict(schema='agentlab.harmony_scenario.v1',scenario=name,
                seedSourceSha256=hashlib.sha256(seed.encode()).hexdigest(),
                iterations=[dict(stage=i,requirement=demands(name,i)) for i in [1,2]],
                recovery='Harness appends invalid ArkTS after successful edits; compiler must fail; Agent repairs preserved edited source',
                oracle='Compiler artifacts/hash plus declared source contracts',
                provenance='AgentLab-owned deterministic template, not a SWE-bench task')
