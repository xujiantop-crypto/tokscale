import hashlib, json, os, subprocess, sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
out=Path('contribution-validation'); out.mkdir(exist_ok=True)
base='b183800d05942c487e273debfa457b49918fa8de'
paths=[Path('crates/tokscale-core/src/'+p) for p in ['sessions/claudecode.rs','sessions/utils.rs','message_cache.rs']]
parser,utils,cache=paths
mode=sys.argv[1]

def run(name,args,check=True,env=None):
    result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace',env=env)
    (out/(name+'.log')).write_text(result.stdout,encoding='utf-8')
    print(name,'exit',result.returncode,flush=True)
    print(result.stdout[-3000:],flush=True)
    if check and result.returncode: raise SystemExit(result.returncode)
    return result

def cli(name):
    fixture_home=(out/'fixture-home').resolve()
    fixture_path=fixture_home/'.claude/projects/-tmp-repro/repro.jsonl'
    fixture_path.parent.mkdir(parents=True,exist_ok=True)
    fixture_path.write_bytes(Path('scripts/advisor-cli-fixture.jsonl').read_bytes())
    config=(out/(name+'-config')).resolve(); config.mkdir(exist_ok=True)
    env=dict(os.environ,TOKSCALE_CONFIG_DIR=str(config),XDG_CACHE_HOME=str(config/'cache'),XDG_CONFIG_HOME=str(config))
    run(name+'-build',['cargo','build','--locked','-p','tokscale-cli'])
    binary=Path('target/debug/tokscale'+('.exe' if os.name=='nt' else '')).resolve()
    result=subprocess.run([str(binary),'models','--json','--no-spinner','--home',str(fixture_home),'--client','claude'],capture_output=True,encoding='utf-8',errors='replace',env=env)
    (out/(name+'.log')).write_text(result.stdout,encoding='utf-8')
    (out/(name+'-stderr.log')).write_text(result.stderr,encoding='utf-8')
    assert result.returncode==0,result.stderr
    obj=json.loads(result.stdout)
    print(name,'models',[(e['model'],e['input'],e['output']) for e in obj['entries']],flush=True)
    (out/(name+'.json')).write_text(json.dumps(obj,indent=2),encoding='utf-8')
    return obj

if mode=='format':
    run('format',['cargo','fmt','--all'])
    changed=subprocess.check_output(['git','diff','--name-only'],encoding='utf-8').splitlines()
    assert set(changed)<=set(p.as_posix() for p in paths),changed
    for p in paths: (out/p.name).write_bytes(p.read_bytes())
elif mode=='baseline':
    fixed={p:p.read_bytes() for p in paths}
    try:
        for p in paths:
            original=subprocess.check_output(['git','show',base+':'+p.as_posix()],encoding='utf-8')
            if p==parser:
                s=p.read_text(encoding='utf-8'); marker='\n#[cfg(test)]\nmod advisor_usage_tests'
                original+=s[s.index(marker):]
            if p==cache:
                s=p.read_text(encoding='utf-8')
                start=s.index('    #[test]\n    #[serial_test::serial]\n    fn advisor_usage_rebuilds_')
                end=s.index('    #[test]\n    fn test_devin_parser_versions_',start)
                marker='    #[test]\n    fn test_devin_parser_versions_'
                original=original.replace(marker,s[start:end]+marker,1)
            p.write_text(original,encoding='utf-8',newline='\n')
        red=run('baseline-advisor',['cargo','test','--locked','-p','tokscale-core','--lib','advisor_usage','--','--nocapture'],False)
        failures=['advisor_usage_is_attributed_without_recounting_main_iterations','advisor_usage_on_later_sidechain_duplicate_merges_complete_tokens','advisor_usage_keeps_separate_calls_for_same_model_and_missing_request_id','advisor_usage_rebuilds_warm_claude_and_mirror_caches_without_losing_history']
        assert red.returncode!=0 and 'test result: FAILED.' in red.stdout,red.stdout[-4000:]
        assert all(any(n in line and 'FAILED' in line for line in red.stdout.splitlines()) for n in failures),red.stdout[-4000:]
        report=cli('baseline-cli')
        assert len(report['entries'])==1 and report['entries'][0]['model']=='claude-opus-5-5',report
        assert report['totalMessages']==1,report
        (out/'baseline-result.json').write_text(json.dumps({'base':base,'expected_failures':failures,'cli_advisor_model_missing':True}),encoding='utf-8')
    finally:
        for p,b in fixed.items():p.write_bytes(b)
elif mode=='final':
    run('fmt-check',['cargo','fmt','--all','--','--check'])
    run('advisor-tests',['cargo','test','--locked','-p','tokscale-core','--lib','advisor_usage','--','--nocapture'])
    run('clippy',['cargo','clippy','--locked','--workspace','--all-features','--','-D','warnings'])
    run('workspace-tests',['cargo','test','--locked','--workspace','--all-features','--no-fail-fast'])
    run('rustdoc',['cargo','doc','--locked','--no-deps','--workspace'],env=dict(os.environ,RUSTDOCFLAGS='-D warnings'))
    report=cli('fixed-cli')
    entries={e['model']:e for e in report['entries']}
    main=entries['claude-opus-5-5']; advisor=entries['claude-fable-5-1']
    assert (main['input'],main['output'],main['cacheRead'],main['cacheWrite'])==(4,779,224791,1763),main
    assert (advisor['input'],advisor['output'])==(114995,2343),advisor
    assert report['totalMessages']==1 and advisor['messageCount']==0,report
    (out/'final-result.json').write_text(json.dumps({'all_required_gates':'passed','source_hashes':{p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}},indent=2),encoding='utf-8')
else:raise ValueError(mode)
