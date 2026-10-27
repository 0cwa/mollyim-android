#!/usr/bin/env python3
"""Check selected localized XML resource parity against pinned Molly and preserve Signal resources."""
import argparse
import replay
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import source_tree

RESOURCE_PATH = re.compile(r'^app/src/main/res/(values[^/]*)/strings2\.xml$')
XML_RESOURCE_PATH = re.compile(r'^app/src/main/res/values[^/]*/[^/]+\.xml$')
AAPT_EQUIVALENCE = {
    'path': 'app/src/main/res/values/strings2.xml',
    'tag': 'string',
    'name': 'MollySocketLink_scan_the_qr_code',
    'target_source_sha256': 'b48b08d61df2bcd73d778a43eabe891486dbc89fbe60cc40f6b20f915228fdf1',
    'candidate_source_sha256': '7e0f9b9033e9ca7b3d50650fa7cd89fcff867ae0abdb4ce9d259bbc5b334b3ac',
    'target_fixture': 'reports/827/inventory/resource-aapt2/source/pinned-target/strings2.xml',
    'candidate_fixture': 'reports/827/inventory/resource-aapt2/source/candidate/strings2.xml',
    'target_element_xml_sha256': '0504e00ca26c672676ce733cde1fa6497bab9b0de29da49c01d4de9871fc43ab',
    'candidate_element_xml_sha256': 'e913acec30c69657c31d4cd765eabf876d39d05aecac87542ae8c2fd4273a722',
    'runtime_text': "Scan the QR code displayed on your MollySocket server's homepage or in the console.",
    'runtime_text_sha256': 'f2b0f701b5560bc9ead7f21738c6378c856d323f32b2e71ffd1f5d554aae04ad',
    'target_dump_sha256': '96e33684eb560461e959d2c1c336ef633b5580a71a793ea3daadd1f411379d1f',
    'candidate_dump_sha256': '6e4cc4cebb47d501cb66cf071aeab60415cf1cda484ab82f4b65bf0e4ba0611f',
    'aapt_version_sha256': '74356fd86dc621b0e73dd382120da390cd01024857fc1c81c2f4196b4d47f165',
    'fixture_manifest_sha256': '388e0cf63ba16dae306795d43158a4b0323c7675c41dc829457698c58d66985d',
    'outputs_hash_manifest_sha256': '49341982b6e28ff8ba14d27afc5b6f2e267bd600e8cdac36cfa93e33156323fa',
    'proof': 'reports/827/inventory/resource-aapt2/aapt2-equivalence.json',
}

def git(repo, *args, text=True):
    return subprocess.check_output(['git','-C',str(repo),*args],text=text,stderr=subprocess.DEVNULL)

def blob(repo, rev, path):
    result=subprocess.run(['git','-C',str(repo),'show',f'{rev}:{path}'],capture_output=True)
    return result.stdout if result.returncode==0 else None

def canonical(element):
    return [element.tag, sorted(element.attrib.items()), element.text,
            [[canonical(child), child.tail] for child in element]]

def parse_items(data, path):
    if data is None: return {}
    try: root=ET.fromstring(data)
    except ET.ParseError as exc: raise ValueError(f'{path}: invalid XML: {exc}') from exc
    found={}
    for element in root:
        name=element.get('name')
        if name is None: continue
        key=(element.tag,name)
        if key in found: raise ValueError(f'{path}: duplicate named resource {key}')
        found[key]=canonical(element)
    return found

def element_sha(element):
    return hashlib.sha256(ET.tostring(element, encoding='utf-8')).hexdigest()

def verify_fixture_sources(repo, target_blob, candidate_blob):
    """Require aapt2 fixture inputs to be the exact pinned Git source blobs."""
    expected = (
        ('target', AAPT_EQUIVALENCE['target_fixture'], target_blob,
         AAPT_EQUIVALENCE['target_source_sha256']),
        ('candidate', AAPT_EQUIVALENCE['candidate_fixture'], candidate_blob,
         AAPT_EQUIVALENCE['candidate_source_sha256']),
    )
    actual_hashes = {}
    for label, relative, source_blob, expected_sha in expected:
        fixture = (repo / relative).read_bytes()
        actual_sha = hashlib.sha256(fixture).hexdigest()
        if source_blob is None or fixture != source_blob or actual_sha != expected_sha:
            raise ValueError(f'{label} aapt2 fixture is not byte-identical to its pinned source blob')
        actual_hashes[label] = actual_sha
    return actual_hashes

def names_fingerprint(keys):
    normalized=sorted((path,tag,name) for path,tag,name in keys)
    return hashlib.sha256(json.dumps(normalized,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def check_resource_parity(repo: Path, write_report=True):
    repo=repo.resolve();manifest=replay.load_inputs(repo/'patches/827',repo/'docs/827/parity-evidence.json')
    base=manifest['signal_base'];target=manifest['molly_expected']
    app_revision=manifest.get('expected_application_commit') or git(repo,'rev-parse','HEAD').strip()
    exclusions=manifest.get('metadata_exclusions',[])
    projected_tree=source_tree.project_tree(repo,app_revision,exclusions)
    expected_tree=manifest.get('expected_tree_sha')
    if expected_tree and projected_tree!=expected_tree:
        raise ValueError(f'projected source tree mismatch: {projected_tree} != {expected_tree}')
    owned=set()
    for feature in manifest['features']:
        owned.update(feature.get('parity_paths',[]))
        owned.update(x['path'] for x in feature.get('integration_paths',[]))
        owned.update(x['path'] for x in feature.get('adaptation_paths',[]))
    resource_paths={p for p in owned if RESOURCE_PATH.fullmatch(p)}
    if not resource_paths: raise ValueError('manifest has no owned localized strings2.xml paths')
    changed_names=git(repo,'diff','--name-only',base,projected_tree,'--','app/src/main/res').splitlines()
    changed_resource_paths={p for p in changed_names if RESOURCE_PATH.fullmatch(p)}
    if changed_resource_paths!=resource_paths:
        raise ValueError('changed strings2.xml paths differ from manifest-owned resource paths: '
                         f'unowned={sorted(changed_resource_paths-resource_paths)}, unchanged_or_missing={sorted(resource_paths-changed_resource_paths)}')
    target_delta_keys=set();candidate_delta_keys=set();per_file=[];resource_mismatches=[];outside_target=[];preserved_entries=0;runtime_equivalent=[]
    for path in sorted(resource_paths):
        before=parse_items(blob(repo,base,path),path+'@base')
        expected=parse_items(blob(repo,target,path),path+'@target')
        current=parse_items(blob(repo,projected_tree,path),path+'@projected')
        keys=set(before)|set(expected)|set(current)
        td={key for key in keys if before.get(key)!=expected.get(key)}
        cd={key for key in keys if before.get(key)!=current.get(key)}
        target_delta_keys.update((path,*key) for key in td)
        candidate_delta_keys.update((path,*key) for key in cd)
        extras=cd-td
        outside_target.extend((path,*key) for key in sorted(extras))
        mismatches=[key for key in sorted(cd) if current.get(key)!=expected.get(key)]
        for key in mismatches:
            candidate_key=(path,*key)
            if candidate_key == (AAPT_EQUIVALENCE['path'],AAPT_EQUIVALENCE['tag'],AAPT_EQUIVALENCE['name']):
                proof_path=repo/AAPT_EQUIVALENCE['proof'];proof=json.loads(proof_path.read_text())
                evidence_dir=repo/'reports/827/inventory/resource-aapt2'
                def evidence_sha(relative): return hashlib.sha256((evidence_dir/relative).read_bytes()).hexdigest()
                hash_manifest=evidence_dir/'output-sha256.txt'
                hashes_ok=(evidence_sha('outputs/target-dump.txt')==AAPT_EQUIVALENCE['target_dump_sha256'] and evidence_sha('outputs/candidate-dump.txt')==AAPT_EQUIVALENCE['candidate_dump_sha256'] and evidence_sha('aapt2-version.txt')==AAPT_EQUIVALENCE['aapt_version_sha256'] and evidence_sha('fixture/AndroidManifest.xml')==AAPT_EQUIVALENCE['fixture_manifest_sha256'] and evidence_sha('output-sha256.txt')==AAPT_EQUIVALENCE['outputs_hash_manifest_sha256'])
                if hashes_ok:
                    for line in hash_manifest.read_text().splitlines():
                        expected_hash,relative=line.split('  ',1)
                        if evidence_sha(relative.replace('reports/827/inventory/resource-aapt2/',''))!=expected_hash: hashes_ok=False;break
                target_dump=(evidence_dir/'outputs/target-dump.txt').read_text();candidate_dump=(evidence_dir/'outputs/candidate-dump.txt').read_text()
                def dumped_value(dump):
                    match=re.search(r'resource [^\n]* string/'+re.escape(AAPT_EQUIVALENCE['name'])+r'\n\s+\(\) "(.*)"',dump)
                    return match.group(1) if match else None
                target_blob=blob(repo,target,path);candidate_blob=blob(repo,projected_tree,path)
                # The aapt2 dumps prove runtime equivalence only for the exact
                # source bytes compiled into the fixtures. Bind those inputs to
                # the pinned Git blobs before accepting the compiled proof.
                try:
                    fixture_hashes=verify_fixture_sources(repo,target_blob,candidate_blob)
                    fixture_sources_ok=True
                except (ValueError, OSError):
                    fixture_hashes={};fixture_sources_ok=False
                target_root=ET.fromstring(target_blob);candidate_root=ET.fromstring(candidate_blob)
                target_element=next(x for x in target_root if x.tag==key[0] and x.get('name')==key[1])
                candidate_element=next(x for x in candidate_root if x.tag==key[0] and x.get('name')==key[1])
                proof_ok=(hashes_ok and fixture_sources_ok and dumped_value(target_dump)==AAPT_EQUIVALENCE['runtime_text'] and dumped_value(candidate_dump)==AAPT_EQUIVALENCE['runtime_text'] and proof.get('status')=='PASS' and proof.get('runtime_text_equal') is True and proof.get('compiled_runtime_text')==AAPT_EQUIVALENCE['runtime_text'] and proof.get('target_source_sha256')==AAPT_EQUIVALENCE['target_source_sha256'] and proof.get('candidate_source_sha256')==AAPT_EQUIVALENCE['candidate_source_sha256'] and proof.get('target_element_xml_sha256')==AAPT_EQUIVALENCE['target_element_xml_sha256'] and proof.get('candidate_element_xml_sha256')==AAPT_EQUIVALENCE['candidate_element_xml_sha256'] and proof.get('target_compiled_runtime_text_sha256')==AAPT_EQUIVALENCE['runtime_text_sha256'] and proof.get('candidate_compiled_runtime_text_sha256')==AAPT_EQUIVALENCE['runtime_text_sha256'] and hashlib.sha256(target_blob).hexdigest()==AAPT_EQUIVALENCE['target_source_sha256'] and hashlib.sha256(candidate_blob).hexdigest()==AAPT_EQUIVALENCE['candidate_source_sha256'] and element_sha(target_element)==AAPT_EQUIVALENCE['target_element_xml_sha256'] and element_sha(candidate_element)==AAPT_EQUIVALENCE['candidate_element_xml_sha256'])
                if proof_ok and target_element.text.startswith('\"') and not target_element.text.endswith('\"') and candidate_element.text==target_element.text+'\"':
                    runtime_equivalent.append(candidate_key);continue
            resource_mismatches.append(candidate_key)
        # Entries in the Signal baseline outside the exact Molly-selected delta must remain intact.
        preserved=[key for key in before if key not in cd and current.get(key)==before[key]]
        preserved_entries+=len(preserved)
        per_file.append({'path':path,'candidate_changed_elements':len(cd),'pinned_target_matches':len(cd)-len(mismatches),
                         'unrelated_baseline_elements_preserved':len(preserved),'candidate_key_set_sha256':names_fingerprint((path,*key) for key in cd)})
    # Every candidate XML resource outside the manifest-selected 33 locale files must still match Signal byte-for-byte.
    base_resources=set(git(repo,'ls-tree','-r','--name-only',base,'--','app/src/main/res').splitlines())
    baseline_xml={p for p in base_resources if XML_RESOURCE_PATH.fullmatch(p)}
    untouched=sorted(baseline_xml-resource_paths);modified_untouched=[]
    for path in untouched:
        if blob(repo,base,path)!=blob(repo,projected_tree,path): modified_untouched.append(path)
    if outside_target or resource_mismatches or modified_untouched:
        raise ValueError(f'resource parity failed: candidate keys outside target delta={len(outside_target)}, value mismatches={len(resource_mismatches)}, unrelated XML files modified={len(modified_untouched)}')
    # Changed keys are path-owned by the manifest; document the exact name set compactly.
    key_names=sorted({name for _,_,name in candidate_delta_keys})
    report={'status':'PASS','method':'Compare named XML elements in pinned Signal baseline, pinned Molly target, and the manifest-pinned projected app tree. Candidate deltas must be a subset of target deltas and equal canonical markup, except one explicitly hash-pinned string whose target/candidate runtime equivalence is independently proven by SDK aapt2 using fixture bytes verified against the pinned source blobs; all other baseline value XML files remain byte-identical to Signal.','revisions':{'signal_base':base,'molly_target':target,'application_commit':app_revision,'projected_tree':projected_tree},'manifest_owned_resource_paths':len(resource_paths),'changed_resource_paths':len(changed_resource_paths),'candidate_changed_elements':len(candidate_delta_keys),'manifest_owned_changed_resource_keys':len(candidate_delta_keys),'manifest_owned_resource_key_set_sha256':names_fingerprint(candidate_delta_keys),'pinned_target_element_matches':len(candidate_delta_keys)-len(resource_mismatches),'raw_exact_element_matches':len(candidate_delta_keys)-len(resource_mismatches)-len(runtime_equivalent),'compiler_proven_runtime_equivalent_elements':len(runtime_equivalent),'compiler_proven_runtime_equivalent_keys':[list(x) for x in runtime_equivalent],'compiler_equivalence_evidence':({'report':AAPT_EQUIVALENCE['proof'],'report_sha256':hashlib.sha256((repo/AAPT_EQUIVALENCE['proof']).read_bytes()).hexdigest(),'target_fixture':AAPT_EQUIVALENCE['target_fixture'],'target_fixture_sha256':fixture_hashes['target'],'candidate_fixture':AAPT_EQUIVALENCE['candidate_fixture'],'candidate_fixture_sha256':fixture_hashes['candidate'],'fixture_bytes_match_pinned_source_blobs':True,'aapt2_version':'Android Asset Packaging Tool (aapt) 2.20-13193326','android_api':36,'runtime_text_sha256':AAPT_EQUIVALENCE['runtime_text_sha256']} if runtime_equivalent else None),'unique_selected_resource_names':len(key_names),'selected_resource_names':key_names,'unrelated_baseline_elements_preserved':preserved_entries,'unrelated_baseline_xml_files_checked':len(untouched),'unrelated_baseline_xml_files_unchanged':len(untouched),'candidate_delta_outside_target_delta':len(outside_target),'value_mismatches':len(resource_mismatches),'files':per_file}
    report_path=repo/'reports/827/inventory/resource-parity.json'
    if write_report:
        report_path.parent.mkdir(parents=True,exist_ok=True);report_path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo',type=Path,default=Path('.'));args=parser.parse_args()
    try: result=check_resource_parity(args.repo);code=0
    except Exception as exc: result={'status':'FAIL','error':str(exc)};code=1
    print(json.dumps({k:v for k,v in result.items() if k not in {'files','selected_resource_names'}},indent=2));return code

if __name__=='__main__':raise SystemExit(main())
