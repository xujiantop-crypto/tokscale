import hashlib,json,os,subprocess,sys
from pathlib import Path

out=Path('contribution-validation');out.mkdir(exist_ok=True)
paths=[Path('crates/tokscale-core/src/sessions/hindsight.rs'),Path('crates/tokscale-core/src/message_cache.rs')]
base='ca270d5281255f3f8fa96e2171fdc17db7153490'
def run(name,args,check=True,env=None):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace',env=env)
    (out/(name+'.log')).write_text(p.stdout,encoding='utf-8')
    print(name,'exit',p.returncode,p.stdout[-2500:],flush=True)
    if check and p.returncode:raise SystemExit(p.returncode)
    return p
fixed={p:p.read_bytes() for p in paths}
fixed_lint=run('windows-workspace-clippy-fixed',['cargo','clippy','--locked','--workspace','--all-features','--','-D','warnings'],False)
if fixed_lint.returncode:
    try:
        for p in paths:p.write_bytes(subprocess.check_output(['git','show',base+':'+p.as_posix()]))
        original=run('windows-workspace-clippy-main',['cargo','clippy','--locked','--workspace','--all-features','--','-D','warnings'],False)
        def errors(s):return [line for line in s.splitlines() if line.startswith('error:')]
        assert original.returncode!=0 and errors(original.stdout)==errors(fixed_lint.stdout),(errors(original.stdout),errors(fixed_lint.stdout))
        (out/'windows-clippy-baseline.json').write_text(json.dumps({'base':base,'same_errors':errors(original.stdout)},indent=2),encoding='utf-8')
    finally:
        for p,b in fixed.items():p.write_bytes(b)
run('windows-core-clippy',['cargo','clippy','--locked','-p','tokscale-core','--all-features','--','-D','warnings'])
run('windows-fmt-check',['cargo','fmt','--all','--','--check'])
run('windows-hindsight',['cargo','test','--locked','-p','tokscale-core','--lib','hindsight','--','--nocapture'])
run('windows-workspace-tests',['cargo','test','--locked','--workspace','--all-features','--no-fail-fast'])
run('windows-rustdoc',['cargo','doc','--locked','--no-deps','--workspace'],env=dict(os.environ,RUSTDOCFLAGS='-D warnings'))
(out/'windows-complete.json').write_text(json.dumps({'runtime_gates':'passed','cli_clippy_baseline':'unchanged','source_hashes':{p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}},indent=2),encoding='utf-8')
