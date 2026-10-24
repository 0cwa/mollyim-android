#!/usr/bin/env python3
"""Check selected localized XML resource parity against pinned Molly and preserve Signal resources."""
import argparse
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

def names_fingerprint(keys):
    normalized=sorted((path,tag,name) for path,tag,name in keys)
    return hashlib.sha256(json.dumps(normalized,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def check_resource_parity(repo: Path, write_report=True):
    repo=repo.resolve();manifest_path=repo/'patches/827/series.yaml';manifest=json.loads(manifest_path.read_text())
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
    target_delta_keys=set();candidate_delta_keys=set();per_file=[];resource_mismatches=[];outside_target=[];preserved_entries=0
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
        for key in mismatches: resource_mismatches.append((path,*key))
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
    report={'status':'PASS','method':'Compare named XML elements in pinned Signal baseline, pinned Molly target, and the manifest-pinned projected app tree. Candidate deltas must be a subset of target deltas with identical canonical tag/attributes/text/child markup; all other baseline value XML files remain byte-identical to Signal.','revisions':{'signal_base':base,'molly_target':target,'application_commit':app_revision,'projected_tree':projected_tree},'manifest_owned_resource_paths':len(resource_paths),'changed_resource_paths':len(changed_resource_paths),'candidate_changed_elements':len(candidate_delta_keys),'manifest_owned_changed_resource_keys':len(candidate_delta_keys),'manifest_owned_resource_key_set_sha256':names_fingerprint(candidate_delta_keys),'pinned_target_element_matches':len(candidate_delta_keys)-len(resource_mismatches),'unique_selected_resource_names':len(key_names),'selected_resource_names':key_names,'unrelated_baseline_elements_preserved':preserved_entries,'unrelated_baseline_xml_files_checked':len(untouched),'unrelated_baseline_xml_files_unchanged':len(untouched),'candidate_delta_outside_target_delta':len(outside_target),'value_mismatches':len(resource_mismatches),'files':per_file}
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
