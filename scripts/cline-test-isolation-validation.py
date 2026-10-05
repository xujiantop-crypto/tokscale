import os,subprocess,sys,json,hashlib
from pathlib import Path
out=Path('contribution-validation-isolation');out.mkdir(exist_ok=True)
path=Path('crates/tokscale-core/src/message_cache.rs');published='9d40a97f0b60b6a4d8c4bf2baf279d9908c3dbac';test='cline_input_rebuilds_predecessor_cache_for_unchanged_transcript'
keys=['CLINE_SESSION_DATA_DIR','CLINE_DATA_DIR','CLINE_DIR']
def run(name,args,env=None):
 p=subprocess.run(args,capture_output=True,encoding='utf-8',errors='replace',env=env);log=p.stdout+p.stderr;(out/(name+'.log')).write_text(log,encoding='utf-8');print(name,p.returncode,log[-1300:],flush=True);return p.returncode,log
def probes(mode):
 results=[]
 for key in keys:
  empty=(out/('empty-'+key)).resolve();empty.mkdir(exist_ok=True);env=dict(os.environ)
  for k in keys:env.pop(k,None)
  env[key]=str(empty);code,log=run(mode+'-'+key,['cargo','test','--locked','-p','tokscale-core','--lib',test,'--','--nocapture'],env)
  if mode=='baseline':assert code!=0 and 'test result: FAILED.'in log and '0 passed; 1 failed;'in log
  else:assert code==0 and '1 passed; 0 failed;'in log
  results.append(dict(variable=key,code=code,expected_assertion_failure=mode=='baseline'))
 return results
if sys.argv[1]=='baseline':
 fixed=path.read_bytes()
 try:
  path.write_bytes(subprocess.check_output(['git','show',published+':'+path.as_posix()]));results=probes('baseline');(out/'baseline-result.json').write_text(json.dumps(dict(published_head=published,probes=results),indent=2),encoding='utf-8')
 finally:path.write_bytes(fixed)
else:
 for name,args in [('fmt',['cargo','fmt','--all','--','--check']),('core-clippy',['cargo','clippy','--locked','-p','tokscale-core','--all-features','--','-D','warnings'])]:
  code,_=run(name,args);assert code==0
 results=probes('fixed');code,_=run('cline-regressions',['cargo','test','--locked','-p','tokscale-core','--lib','cline_input']);assert code==0
 code,_=run('core-suite',['cargo','test','--locked','-p','tokscale-core','--all-features']);assert code==0
 source={p:hashlib.sha256(Path(p).read_bytes()).hexdigest()for p in ['crates/tokscale-core/src/message_cache.rs','crates/tokscale-core/src/sessions/cline.rs']}
 (out/'message_cache.rs').write_bytes(path.read_bytes());(out/'final-result.json').write_text(json.dumps(dict(probes=results,core_suite='passed',core_clippy='passed',fmt='passed',source_hashes=source),indent=2),encoding='utf-8')
