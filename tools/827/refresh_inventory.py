#!/usr/bin/env python3
"""Refresh live manifest ownership and hunk coordinates from the pinned Git trees."""
import argparse
import replay
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path

import validate_inventory as vi

def write_tsv(path, rows):
    if not rows: raise ValueError(f'no rows for {path}')
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),delimiter='\t',lineterminator='\n')
        writer.writeheader();writer.writerows(rows)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo',type=Path,default=Path('.'));args=parser.parse_args()
    repo=args.repo.resolve();mp=repo/'patches/827/base';manifest=replay.load_inputs(mp.parent, repo/'docs/827/parity-evidence.json');base=manifest['signal_base'];target=manifest['molly_expected'];head=vi.git(repo,'rev-parse','HEAD').strip()
    diff_paths={p for _,_,p in vi.target_diff_records(repo,base,target)}
    source_by_path={};mailbox_by_path={}
    for feature in manifest['features']:
        for patch in feature['patches']:
            text=(mp.parent/patch['path']).read_text(errors='replace')
            paths=set(re.findall(r'^diff --git a/(.*?) b/.*$',text,re.M))
            for p in paths:
                source_by_path.setdefault(p,[]).extend(patch.get('source_commit_shas',[]))
                mailbox_by_path.setdefault(p,[]).append(patch.get('mailbox_commit_sha',''))
    entry={}
    for feature in manifest['features']:
        for p in feature.get('parity_paths',[]): entry.setdefault(p,[]).append(('full-file-parity',''))
        for x in feature.get('integration_paths',[]):
            for frag in x['fragments']:entry.setdefault(x['path'],[]).append(('anchored-fragment',frag['id']))
        for x in feature.get('adaptation_paths',[]):entry.setdefault(x['path'],[]).append(('adaptation',''))
        for x in feature.get('added_paths',[]):entry.setdefault(x if isinstance(x,str) else x['path'],[]).append(('added-target-absent',''))
        for x in feature.get('overlay_paths',[]):entry.setdefault(x if isinstance(x,str) else x['path'],[]).append(('build-validation-overlay',''))
    for x in manifest.get('added_paths',[]):entry.setdefault(x if isinstance(x,str) else x['path'],[]).append(('added-target-absent',''))
    for x in manifest.get('overlay_paths',[]):entry.setdefault(x if isinstance(x,str) else x['path'],[]).append(('build-validation-overlay',''))
    led=[]
    msha=replay.audit_digest(manifest)
    def find_meta(p):
        for f in manifest['features']:
            for x in f.get('adaptation_paths',[]):
                if x['path']==p:return x.get('target_sha256',''),x.get('expected_replay_sha256','')
            for x in f.get('added_paths',[]):
                if (x if isinstance(x,str) else x['path'])==p and isinstance(x,dict):return '',x.get('expected_replay_sha256','')
            for x in f.get('overlay_paths',[]):
                if (x if isinstance(x,str) else x['path'])==p and isinstance(x,dict):return x.get('target_sha256',''),x.get('expected_replay_sha256','')
            if p in f.get('parity_paths',[]):return 'tree-equality','tree-equality'
            for x in f.get('integration_paths',[]):
                if x['path']==p:return ';'.join(z['target_sha256'] for z in x['fragments']),' '
        return '',''
    for p,roles in sorted(entry.items()):
        role=';'.join(dict.fromkeys(x[0] for x in roles)); fragments=';'.join(x[1] for x in roles if x[1])
        fid=next(f['id'] for f in manifest['features'] if p in f.get('parity_paths',[]) or any(x['path']==p for x in f.get('integration_paths',[])) or any(x['path']==p for x in f.get('adaptation_paths',[])) or any((x if isinstance(x,str) else x['path'])==p for x in f.get('added_paths',[])) or any((x if isinstance(x,str) else x['path'])==p for x in f.get('overlay_paths',[])))
        th,eh=find_meta(p)
        claim='full path' if 'full-file-parity' in role else 'fragment only' if 'anchored-fragment' in role else 'none; target absent' if 'added-target-absent' in role else 'no; adaptation/validation overlay'
        led.append({'path':p,'feature_id':fid,'manifest_role':role,'fragment_ids':fragments,'present_in_pinned_target_diff':str(p in diff_paths).lower(),'target_parity_claim':claim,'target_sha256':th,'expected_replay_sha256':eh,'molly_source_commit_shas':';'.join(dict.fromkeys(x for x in source_by_path.get(p,[]) if x)),'reconstruction_mailbox_commit_shas':';'.join(dict.fromkeys(x for x in mailbox_by_path.get(p,[]) if x)),'inputs_sha256':msha})
    hunk_rows=[]
    def add_hunk(fid,p,ownership,tree,start,end,frag='',target_sha=''):
        hunk_rows.append({'feature_id':fid,'path':p,'ownership':ownership,'coordinate_tree':tree,'start_line':start,'end_line':end,'fragment_id':frag,'target_sha256':target_sha,'reconstruction_mailbox_sha':';'.join(dict.fromkeys(mailbox_by_path.get(p,[]))),'molly_origin_candidate':';'.join(dict.fromkeys(source_by_path.get(p,[])))})
    for feature in manifest['features']:
        for p in feature.get('parity_paths',[]):
            data=vi.blob(repo,target,p); end=max(1,data.count(b'\n')+(not data.endswith(b'\n')))
            add_hunk(feature['id'],p,'full-path exact parity','pinned Molly target',1,end,'',hashlib.sha256(data).hexdigest())
        for item in feature.get('integration_paths',[]):
            p=item['path'];data=vi.blob(repo,target,p)
            for frag in item['fragments']:
                a=frag['start_anchor'].encode();b=frag['end_anchor'].encode();s=data.find(a);e=data.find(b,s+len(a)) if s>=0 else -1
                if s<0 or e<0:raise ValueError(f'cannot locate target anchor {p}:{frag["id"]}')
                add_hunk(feature['id'],p,'anchored fragment '+frag['id'],'pinned Molly target',str(vi.line_num(data,s)),str(vi.line_num(data,e+len(b)-1)),frag['id'],frag['target_sha256'])
        for item in feature.get('adaptation_paths',[]):
            p=item['path']
            for start,end in vi.line_ranges(repo,base,head,p):add_hunk(feature['id'],p,'adaptation patch hunk','reconstructed candidate vs Signal base',str(start),str(end),'',item['target_sha256'])
        for item in feature.get('added_paths',[]):
            p=item if isinstance(item,str) else item['path'];entry_data=vi.blob(repo,head,p)
            ranges=vi.line_ranges(repo,base,head,p) or [(1,max(1,entry_data.count(b'\n')+(not entry_data.endswith(b'\n'))))]
            for start,end in ranges:add_hunk(feature['id'],p,'added target-absent path','reconstructed candidate vs Signal base',str(start),str(end),'', '')
        for item in feature.get('overlay_paths',[]):
            p=item if isinstance(item,str) else item['path']
            for start,end in vi.line_ranges(repo,base,head,p):add_hunk(feature['id'],p,'build-validation overlay hunk','reconstructed candidate vs Signal base',str(start),str(end),'',item.get('target_sha256','') if isinstance(item,dict) else '')
    for item in manifest.get('added_paths',[]):
        p=item if isinstance(item,str) else item['path'];data=vi.blob(repo,head,p)
        for start,end in vi.line_ranges(repo,base,head,p) or [(1,max(1,data.count(b'\n')+(not data.endswith(b'\n'))))]:add_hunk('validation',p,'added target-absent path','reconstructed candidate vs Signal base',str(start),str(end),'','')
    for item in manifest.get('overlay_paths',[]):
        p=item if isinstance(item,str) else item['path']
        for start,end in vi.line_ranges(repo,base,head,p):add_hunk('validation',p,'build-validation overlay hunk','reconstructed candidate vs Signal base',str(start),str(end),'',item.get('target_sha256','') if isinstance(item,dict) else '')
    inv=repo/'reports/827/inventory';write_tsv(inv/'current-series-owned.tsv',led);write_tsv(inv/'selected-hunks.tsv',hunk_rows)
    summary=json.loads((inv/'summary.json').read_text());summary['selected_boundary']['historical_target_paths']=80;summary['selected_boundary']['live_manifest_ledger']='reports/827/inventory/current-series-owned.tsv';summary['selected_boundary']['live_manifest_snapshot']={'paths':len(led),'target_diff_paths':sum(r['present_in_pinned_target_diff']=='true' for r in led),'target_absent_paths':sum('added-target-absent' in r['manifest_role'] for r in led),'roles':dict(__import__('collections').Counter(role for r in led for role in r['manifest_role'].split(';')))};summary['selected_boundary']['live_manifest_ledger_sha256']=hashlib.sha256((inv/'current-series-owned.tsv').read_bytes()).hexdigest();summary['selected_boundary']['hunk_coordinate_tsv_sha256']=hashlib.sha256((inv/'selected-hunks.tsv').read_bytes()).hexdigest()
    (inv/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({'current_paths':len(led),'hunk_rows':len(hunk_rows),'roles':summary['selected_boundary']['live_manifest_snapshot']['roles']},indent=2))
if __name__=='__main__':main()
