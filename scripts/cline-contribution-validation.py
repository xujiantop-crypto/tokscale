import hashlib,json,os,subprocess,sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
out=Path('contribution-validation');out.mkdir(exist_ok=True)
base='b183800d05942c487e273debfa457b49918fa8de'
paths=[Path('crates/tokscale-core/src/'+p)for p in ['sessions/cline.rs','message_cache.rs']]
def run(name,args,check=True,env=None):
 p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace',env=env)
 (out/(name+'.log')).write_text(p.stdout,encoding='utf-8');print(name,'exit',p.returncode,flush=True);print(p.stdout[-1800:],flush=True)
 if check and p.returncode:raise SystemExit(p.returncode)
 return p

def restore_base_with_tests():
 for p in paths:
  s=subprocess.check_output(['git','show',base+':'+p.as_posix()]).decode('utf-8')
  if p.name=='cline.rs':s+=Path('scripts/cline-parser-tests.rs').read_text(encoding='utf-8')
  else:
   marker='    #[test]\n    fn test_devin_parser_versions_'
   assert marker in s;s=s.replace(marker,Path('scripts/cline-cache-tests.rs').read_text(encoding='utf-8')+marker,1)
  p.write_text(s,encoding='utf-8',newline='\n')

def cli(name):
 home=(out/'fixture-home').resolve();path=home/'.cline/data/sessions/s1/s1.messages.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(Path('scripts/cline-cli-fixture.json').read_bytes())
 config=(out/(name+'-config')).resolve();config.mkdir(exist_ok=True)
 env=dict(os.environ,TOKSCALE_CONFIG_DIR=str(config),XDG_CACHE_HOME=str(config/'cache'),XDG_CONFIG_HOME=str(config))
 run(name+'-build',['cargo','build','--locked','-p','tokscale-cli'])
 binary=Path('target/debug/tokscale'+('.exe'if os.name=='nt'else'')).resolve()
 p=subprocess.run([str(binary),'graph','--no-spinner','--home',str(home),'--client','cline'],capture_output=True,encoding='utf-8',errors='replace',env=env)
 (out/(name+'-stdout.log')).write_text(p.stdout,encoding='utf-8');(out/(name+'-stderr.log')).write_text(p.stderr,encoding='utf-8');assert p.returncode==0,p.stderr
 obj=json.loads(p.stdout);(out/(name+'.json')).write_text(json.dumps(obj,indent=2),encoding='utf-8');day=obj['contributions'][0];summary={'day_total':day['totals']['tokens'],'day_breakdown_sum':sum(day['tokenBreakdown'].get(k,0)for k in ['input','output','cacheRead','cacheWrite','reasoning']),'client_sum':sum(sum(c['tokens'].get(k,0)for k in ['input','output','cacheRead','cacheWrite','reasoning'])for c in day['clients'])};print(name,summary,flush=True);return obj,summary

mode=sys.argv[1]
if mode=='format':
 run('format',['cargo','fmt','--all']);changed=subprocess.check_output(['git','diff','--name-only'],encoding='utf-8').splitlines();assert set(changed)<=set(p.as_posix()for p in paths),changed
 for p in paths:(out/p.name).write_bytes(p.read_bytes())
elif mode=='baseline':
 fixed={p:p.read_bytes()for p in paths}
 try:
  restore_base_with_tests();red=run('baseline-tests',['cargo','test','--locked','-p','tokscale-core','--lib','cline_input','--','--nocapture'],False)
  expected=['cline_input_cannot_be_negative_when_cache_exceeds_gross_input','cline_input_keeps_cache_only_messages_without_reported_cost','cline_input_daily_session_and_streamed_totals_agree','cline_input_rebuilds_predecessor_cache_for_unchanged_transcript']
  assert red.returncode!=0 and 'test result: FAILED.'in red.stdout
  assert all(any(n in line and 'FAILED'in line for line in red.stdout.splitlines())for n in expected),red.stdout[-4000:]
  assert '4 failed'in red.stdout and '1 passed'in red.stdout,red.stdout[-4000:]
  obj,summary=cli('baseline-cli');assert summary=={'day_total':20,'day_breakdown_sum':160,'client_sum':160},summary
  (out/'baseline-result.json').write_text(json.dumps({'base':base,'expected_failures':expected,'control_passed':True,'graph':summary}),encoding='utf-8')
 finally:
  for p,b in fixed.items():p.write_bytes(b)
elif mode=='final':
 run('fmt-check',['cargo','fmt','--all','--','--check']);run('cline-tests',['cargo','test','--locked','-p','tokscale-core','--lib','cline_input','--','--nocapture'])
 lint=run('workspace-clippy',['cargo','clippy','--locked','--workspace','--all-features','--','-D','warnings'],os.name!='nt')
 if os.name=='nt':
  if lint.returncode:
   fixed={p:p.read_bytes()for p in paths}
   try:
    for p in paths:p.write_bytes(subprocess.check_output(['git','show',base+':'+p.as_posix()]))
    original=run('windows-base-clippy',['cargo','clippy','--locked','--workspace','--all-features','--','-D','warnings'],False)
    def diagnostics(s):return sorted(l.strip()for l in s.splitlines()if l.startswith('error:')or l.lstrip().startswith('-->'))
    assert original.returncode!=0 and diagnostics(original.stdout)==diagnostics(lint.stdout)
    (out/'windows-clippy-baseline.json').write_text(json.dumps({'base':base,'identical_diagnostics':diagnostics(original.stdout),'fixed_exit':lint.returncode,'base_exit':original.returncode},indent=2),encoding='utf-8')
   finally:
    for p,b in fixed.items():p.write_bytes(b)
  run('core-clippy',['cargo','clippy','--locked','-p','tokscale-core','--all-features','--','-D','warnings'])
 run('workspace-tests',['cargo','test','--locked','--workspace','--all-features','--no-fail-fast'])
 run('rustdoc',['cargo','doc','--locked','--no-deps','--workspace'],env=dict(os.environ,RUSTDOCFLAGS='-D warnings'))
 obj,summary=cli('fixed-cli');assert summary=={'day_total':160,'day_breakdown_sum':160,'client_sum':160},summary
 day=obj['contributions'][0];assert day['totals']['messages']==1 and abs(day['totals']['cost']-0.01)<1e-9
 (out/'final-result.json').write_text(json.dumps({'runtime_gates':'passed','workspace_clippy':'passed'if not lint.returncode else 'failed; identical pinned-base diagnostics','graph':summary,'source_hashes':{p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in paths}},indent=2),encoding='utf-8')
else:raise ValueError(mode)
