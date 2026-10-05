from pathlib import Path
# Reuse only helper definitions, not the red/green entrypoint.
exec(Path('scripts/advisor-contribution-validation.py').read_text(encoding='utf-8').split("if mode=='format':")[0])
fixed={p:p.read_bytes() for p in paths}
lint=run('windows-workspace-clippy-fixed',['cargo','clippy','--locked','--workspace','--all-features','--','-D','warnings'],False)
if lint.returncode:
    try:
        for p in paths:p.write_bytes(subprocess.check_output(['git','show',base+':'+p.as_posix()]))
        original=run('windows-workspace-clippy-main',['cargo','clippy','--locked','--workspace','--all-features','--','-D','warnings'],False)
        def diagnostics(s):
            return sorted(line.strip() for line in s.splitlines() if line.startswith('error:') or line.lstrip().startswith('-->'))
        assert original.returncode!=0 and diagnostics(original.stdout)==diagnostics(lint.stdout),(diagnostics(original.stdout),diagnostics(lint.stdout))
        (out/'windows-clippy-baseline.json').write_text(json.dumps({'base':base,'identical_diagnostics':diagnostics(original.stdout),'fixed_exit':lint.returncode,'base_exit':original.returncode},indent=2),encoding='utf-8')
    finally:
        for p,b in fixed.items():p.write_bytes(b)
run('windows-core-clippy',['cargo','clippy','--locked','-p','tokscale-core','--all-features','--','-D','warnings'])
run('windows-fmt-check',['cargo','fmt','--all','--','--check'])
run('windows-advisor-tests',['cargo','test','--locked','-p','tokscale-core','--lib','advisor_usage','--','--nocapture'])
run('windows-workspace-tests',['cargo','test','--locked','--workspace','--all-features','--no-fail-fast'])
run('windows-rustdoc',['cargo','doc','--locked','--no-deps','--workspace'],env=dict(os.environ,RUSTDOCFLAGS='-D warnings'))
report=cli('windows-fixed-cli')
entries={e['model']:e for e in report['entries']}; main=entries['claude-opus-5-5']; advisor=entries['claude-fable-5-1']
assert (main['input'],main['output'],main['cacheRead'],main['cacheWrite'])==(4,779,224791,1763),main
assert (advisor['input'],advisor['output'])==(114995,2343),advisor
assert report['totalMessages']==1 and advisor['messageCount']==0,report
(out/'windows-complete.json').write_text(json.dumps({'runtime_gates':'passed','core_clippy':'passed','workspace_clippy':'passed' if not lint.returncode else '6 CLI diagnostics identical on pinned base','source_hashes':{p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}},indent=2),encoding='utf-8')
