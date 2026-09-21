#!/usr/bin/env python3
"""Compose one published component from a donor composition into a frozen base."""
import argparse
import copy
import hashlib
import importlib.util
import json
import urllib.parse
from pathlib import Path


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), Path(__file__).with_name(name+'.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def load(directory):
    raw = (directory/'environment-lock.json').read_bytes()
    publication = json.loads((directory/'publication.json').read_bytes())
    lock = json.loads(raw)
    module('validate-composition-release').validate(publication, lock, raw)
    return publication, lock



def replacement_donor(base, manifest, component, origin=None):
    """A component producer declares one row, its contracts and published assets."""
    if manifest['schema'] != 'agentlab.component_update.v1' or manifest['component'] != component:
        raise ValueError('component update descriptor does not match selected role')
    pub, lock = copy.deepcopy(base)
    value = copy.deepcopy(manifest['value'])
    if origin:
        for field in ('artifact','descriptor','templateInventory'):
            if field in value: value[field] = urllib.parse.urljoin(origin,value[field])
    if component == 'session-sdk':
        pub['sessionSdk'] = value
    elif component == 'control':
        pub['smoke']['control'] = value['artifact']
        pub['controllerSourceShort'] = value['sourceRevision'][:8]
    else:
        kind,slot = component.split(':',1)
        collection = {'pack':'components','image':'images'}[kind]
        matches = [i for i,row in enumerate(lock[collection]) if row['slot']==slot and row['platform']==pub['platform']]
        if len(matches)!=1: raise ValueError('component update slot is missing or ambiguous')
        lock[collection][matches[0]] = value
        node = copy.deepcopy(manifest['graphNode'])
        binding = {'kind':'pack-slot' if kind=='pack' else 'image-slot','slot':slot}
        if node['binding'] != binding or node['platform'] != pub['platform']:
            raise ValueError('component update contract binding differs')
        matches = [i for i,n in enumerate(lock['componentGraph']['nodes']) if n['binding']==binding and n['platform']==pub['platform']]
        if len(matches)!=1: raise ValueError('component contract slot is missing or ambiguous')
        lock['componentGraph']['nodes'][matches[0]] = node
        if component=='pack:release':
            pub['sourceRevision'] = lock['sourceRevision'] = manifest['sourceRevision']
    assets = {a['url']:a for a in pub['assets']}
    assets.update({a['url']:copy.deepcopy(a) for a in manifest['assets']})
    pub['assets'] = list(assets.values())
    return pub,lock

def compose(base, donor, component, tag):
    original, old_lock = base
    replacement, donor_lock = donor
    if not tag.startswith('candidate-'):
        raise ValueError('new tag must be a candidate')
    pub, lock = copy.deepcopy(original), copy.deepcopy(old_lock)
    before_urls, after_urls = set(), set()
    if component in ('session-sdk', 'control'):
        if component == 'session-sdk':
            before, after = original['sessionSdk'], replacement['sessionSdk']
            pub['sessionSdk'] = copy.deepcopy(after)
            before_urls.add(before['artifact']); after_urls.add(after['artifact'])
            before_action = before.get('actionQualification')
            after_action = after.get('actionQualification')
            if before_action:
                before_urls.add(before_action['artifact'])
            if after_action:
                after_urls.add(after_action['artifact'])
        else:
            before, after = original['smoke']['control'], replacement['smoke']['control']
            pub['smoke']['control'] = after
            pub['controllerSourceShort'] = replacement['controllerSourceShort']
            before_urls.add(before); after_urls.add(after)
    else:
        kind, slot = component.split(':', 1)
        collection = {'pack':'components', 'image':'images'}[kind]
        def selected(items):
            matches = [row for row in items if row['slot'] == slot and row['platform'] == original['platform']]
            if len(matches) != 1:
                raise ValueError('component must resolve to one platform slot')
            return matches[0]
        before, after = selected(old_lock[collection]), selected(donor_lock[collection])
        index = lock[collection].index(before)
        # Deployment binding belongs to the base; donor supplies artifact identity.
        after = copy.deepcopy(after)
        for field in ('slot','mountTarget','required','enabled'):
            if field in before: after[field] = before[field]
        lock[collection][index] = after
        before_urls.update(before[field] for field in ('artifact','descriptor'))
        after_urls.update(after[field] for field in ('artifact','descriptor'))
        binding = {'kind': 'pack-slot' if kind == 'pack' else 'image-slot', 'slot':slot}
        nodes = [n for n in donor_lock['componentGraph']['nodes'] if n['binding'] == binding and n['platform'] == original['platform']]
        if len(nodes) != 1: raise ValueError('replacement contract node is missing or ambiguous')
        matches = [i for i,n in enumerate(lock['componentGraph']['nodes']) if n['binding'] == binding and n['platform'] == original['platform']]
        if len(matches) != 1: raise ValueError('base contract node is missing or ambiguous')
        lock['componentGraph']['nodes'][matches[0]] = copy.deepcopy(nodes[0])
        if component == 'pack:release':
            pub['sourceRevision'] = lock['sourceRevision'] = replacement['sourceRevision']
            pub['smoke']['pack'] = after['artifact']
    if before == after: raise ValueError('component is unchanged; no upgrade candidate created')
    if original['platform'] != replacement['platform']: raise ValueError('replacement platform differs')
    graph = lock['componentGraph']
    resolved = {}
    for node in graph['nodes']:
        contracts = resolved.setdefault(node['platform'], {})
        for key,value in node.get('provides', {}).items():
            if key in contracts: raise ValueError('duplicate contract provider')
            contracts[key] = value
    graph['resolvedContracts'] = resolved
    donor_assets = {a['url']:a for a in replacement['assets']}
    pub['assets'] = [a for a in pub['assets'] if a['url'] not in before_urls-after_urls and a['url'] not in after_urls]
    pub['assets'] += [copy.deepcopy(donor_assets[url]) for url in sorted(after_urls)]
    for key in ('qualifiedReleaseTag','compositionIdentity','environmentLockUrl','qualificationUrl',
                'previousPublicationUrl','previousPublicationSha256','activationPolicy','sourceChannelOrCandidate',
                'sourcePublicationSha256','qualification'):
        pub.pop(key, None)
    pub.update(schema='agentlab.reference_publication.v1', status='candidate', tag=tag,
               activated=False, componentPayloadsUploaded=False,
               gates={check:'not_run' for check in module('channel-plan').BASE})
    raw = (json.dumps(lock, indent=2)+'\n').encode()
    pub['environmentLockSha256'] = hashlib.sha256(raw).hexdigest()
    receipt = dict(schema='agentlab.component_upgrade.v1', component=component,
                   basePublicationSha256=module('channel-plan').digest(original),
                   donorPublicationSha256=module('channel-plan').digest(replacement),
                   before=before, after=after, rebuildComponents=False)
    pub['componentUpgrade'] = receipt
    module('validate-composition-release').validate(pub, lock, raw)
    return pub, lock, raw, receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base','output'): parser.add_argument('--'+name, type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--donor', type=Path)
    source.add_argument('--replacement', type=Path, help='component producer update descriptor')
    parser.add_argument('--component', required=True, help='session-sdk, control, pack:<slot>, image:<slot>')
    parser.add_argument('--tag', required=True)
    parser.add_argument('--replacement-url', help='original descriptor URL for relative metadata references')
    args = parser.parse_args()
    base = load(args.base)
    donor = load(args.donor) if args.donor else replacement_donor(base,json.loads(args.replacement.read_bytes()),args.component,args.replacement_url)
    pub, lock, raw, receipt = compose(base, donor, args.component, args.tag)
    if args.replacement:
        receipt.pop('donorPublicationSha256')
        receipt['replacementDescriptorSha256'] = hashlib.sha256(args.replacement.read_bytes()).hexdigest()
        receipt['replacementDescriptorUrl'] = args.replacement_url
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'environment-lock.json').write_bytes(raw)
    for name,value in [('publication',pub),('component-upgrade',receipt)]:
        (args.output/(name+'.json')).write_text(json.dumps(value, indent=2)+'\n')
    print(json.dumps(receipt))
