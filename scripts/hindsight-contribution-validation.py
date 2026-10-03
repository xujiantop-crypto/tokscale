import json,subprocess,sys
from pathlib import Path
out=Path('contribution-validation');out.mkdir(exist_ok=True)
parser=Path('crates/tokscale-core/src/sessions/hindsight.rs')
cache=Path('crates/tokscale-core/src/message_cache.rs')
def run(name,args,check=True,env=None):
    result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace',env=env)
    (out/(name+'.log')).write_text(result.stdout,encoding='utf-8')
    print(name,'exit',result.returncode,flush=True)
    print(result.stdout[-3500:],flush=True)
    if check and result.returncode:raise SystemExit(result.returncode)
    return result
mode=sys.argv[1]
if mode=='format':
    run('format',['cargo','fmt','--all'])
    changed=subprocess.check_output(['git','diff','--name-only'],encoding='utf-8').splitlines()
    assert set(changed)<=set([parser.as_posix(),cache.as_posix()]),changed
    (out/'final-parser.rs').write_bytes(parser.read_bytes())
    (out/'final-cache.rs').write_bytes(cache.read_bytes())
    print('Formatted paths:',changed)
elif mode=='baseline':
    fixed=parser.read_text(encoding='utf-8')
    marker='\n#[cfg(test)]\nmod cache_token_tests'
    original=subprocess.check_output(['git','show','ca270d5281255f3f8fa96e2171fdc17db7153490:'+parser.as_posix()],text=True,encoding='utf-8')
    parser.write_text(original+fixed[fixed.index(marker):],encoding='utf-8',newline='\n')
    cache.write_text(cache.read_text(encoding='utf-8').replace('ClientId::Hindsight => 2,','ClientId::Hindsight => 1,'),encoding='utf-8',newline='\n')
    try:
        red=run('baseline-hindsight',['cargo','test','--locked','-p','tokscale-core','--lib','hindsight','--','--nocapture'],False)
        assert red.returncode!=0 and 'test result: FAILED.' in red.stdout,red.stdout[-4000:]
        failures=['splits_cache_inclusive_adapter_usage_without_inflating_totals','retains_fully_cached_input_with_no_output','prices_cached_input_only_at_the_cache_rate','hindsight_v1_shards_reparse_cache_inclusive_usage']
        assert all(any(name in line and 'FAILED' in line for line in red.stdout.splitlines()) for name in failures),red.stdout[-4000:]
        (out/'baseline-result.json').write_text(json.dumps({'production_base':'ca270d5281255f3f8fa96e2171fdc17db7153490','expected_failures':failures,'exit':red.returncode},indent=2),encoding='utf-8')
    finally:
        parser.write_bytes((out/'final-parser.rs').read_bytes())
        cache.write_bytes((out/'final-cache.rs').read_bytes())
elif mode=='final':
    run('fmt-check',['cargo','fmt','--all','--','--check'])
    run('hindsight-tests',['cargo','test','--locked','-p','tokscale-core','--lib','hindsight','--','--nocapture'])
    run('clippy',['cargo','clippy','--locked','--workspace','--all-features','--','-D','warnings'])
    run('workspace-tests',['cargo','test','--locked','--workspace','--all-features','--no-fail-fast'])
    import os
    env=dict(os.environ,RUSTDOCFLAGS='-D warnings')
    run('rustdoc',['cargo','doc','--locked','--no-deps','--workspace'],env=env)
    (out/'final-result.json').write_text(json.dumps({'all_required_gates':'passed'},indent=2),encoding='utf-8')
else:raise ValueError(mode)
