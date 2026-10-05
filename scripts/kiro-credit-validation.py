import hashlib, json, os, subprocess
from pathlib import Path
out = Path('kiro-credit-validation')
out.mkdir(exist_ok=True)
results = []

def run(name, args, env=None):
    p = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', env=env)
    log = p.stdout + p.stderr
    (out / (name + '.log')).write_text(log, encoding='utf-8')
    print(name, p.returncode, log[-3000:], flush=True)
    results.append(dict(name=name, args=args, exit_code=p.returncode))
    (out / 'checks.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    assert p.returncode == 0
    return log

run('format', ['cargo', 'fmt', '--all'])
sources = ['crates/tokscale-core/src/sessions/kiro.rs', 'crates/tokscale-core/src/message_cache.rs']
hashes = {}
for source in sources:
    path = Path(source)
    (out / path.name).write_bytes(path.read_bytes())
    hashes[source] = hashlib.sha256(path.read_bytes()).hexdigest()
(out / 'source-hashes.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
run('fmt-check', ['cargo', 'fmt', '--all', '--', '--check'])
log = run('kiro-cli-regressions', ['cargo', 'test', '--locked', '-p', 'tokscale-core', '--lib', 'kiro_cli', '--', '--nocapture'])
assert 'REPRO credited total=0.033000' in log
assert 'REPRO control total=0.031700' in log
run('workspace-clippy', ['cargo', 'clippy', '--locked', '--workspace', '--all-features', '--', '-D', 'warnings'])
run('workspace-tests', ['cargo', 'test', '--locked', '--workspace', '--all-features', '--no-fail-fast'])
if os.name != 'nt':
    env = dict(os.environ, RUSTDOCFLAGS='-D warnings')
    run('rustdoc', ['cargo', 'doc', '--locked', '--no-deps', '--workspace'], env)
(out / 'result.json').write_text(json.dumps(dict(checks=results, source_hashes=hashes), indent=2), encoding='utf-8')
