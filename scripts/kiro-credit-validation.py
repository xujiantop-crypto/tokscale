import hashlib, json, re, subprocess
from pathlib import Path
out = Path('kiro-credit-validation')
out.mkdir(exist_ok=True)
results = []

def run(name, args, expected=0):
    p = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace')
    log = p.stdout + p.stderr
    (out / (name + '.log')).write_text(log, encoding='utf-8')
    print(name, p.returncode, log[-3000:], flush=True)
    results.append(dict(name=name, args=args, exit_code=p.returncode, expected_exit=expected))
    (out / 'checks.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    assert p.returncode == expected
    return log

sources = ['crates/tokscale-core/src/sessions/kiro.rs', 'crates/tokscale-core/src/message_cache.rs']
hashes = {}
for source in sources:
    path = Path(source)
    (out / path.name).write_bytes(path.read_bytes())
    hashes[source] = hashlib.sha256(path.read_bytes()).hexdigest()
(out / 'source-hashes.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
run('fmt-check', ['cargo', 'fmt', '--all', '--', '--check'])
run('core-clippy', ['cargo', 'clippy', '--locked', '-p', 'tokscale-core', '--all-features', '--', '-D', 'warnings'])
clippy = ['cargo', 'clippy', '--locked', '--workspace', '--all-features', '--', '-D', 'warnings']
fixed_log = run('windows-workspace-clippy', clippy, expected=101)
base = 'd4d1c751856e25913bce97bfbd7b254308863239'
fixed = {source: Path(source).read_bytes() for source in sources}
try:
    for source in sources:
        Path(source).write_bytes(subprocess.check_output(['git', 'show', base + ':' + source]))
    baseline_log = run('windows-default-branch-clippy', clippy, expected=101)
finally:
    for source, content in fixed.items():
        Path(source).write_bytes(content)
signatures = lambda log: re.findall(r'^error: (.+)\n\s*--> ([^\n]+)', log, re.MULTILINE)
assert len(signatures(fixed_log)) == 6
assert signatures(fixed_log) == signatures(baseline_log)
assert all('tokscale-cli' in location for _, location in signatures(fixed_log))
(out / 'windows-clippy-baseline-comparison.json').write_text(json.dumps(dict(base=base, identical_diagnostics=signatures(fixed_log)), indent=2), encoding='utf-8')
run('workspace-tests', ['cargo', 'test', '--locked', '--workspace', '--all-features', '--no-fail-fast'])
assert all(hashlib.sha256(Path(source).read_bytes()).hexdigest() == digest for source, digest in hashes.items())
(out / 'result.json').write_text(json.dumps(dict(checks=results, source_hashes=hashes, workspace_windows_clippy='six inherited CLI diagnostics reproduced on default branch'), indent=2), encoding='utf-8')
