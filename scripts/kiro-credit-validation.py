import subprocess
from pathlib import Path
out = Path('kiro-credit-validation')
out.mkdir(exist_ok=True)
args = ['cargo', 'test', '--locked', '-p', 'tokscale-core', '--lib', 'test_kiro_cli_credits_do_not_double_count_token_pricing', '--', '--nocapture']
p = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace')
log = p.stdout + p.stderr
(out / 'baseline.log').write_text(log, encoding='utf-8')
print(log[-7000:], flush=True)
assert p.returncode != 0
assert '0 passed; 1 failed;' in log
assert 'REPRO control total=0.031700' in log
assert 'REPRO credited total=0.041000' in log
assert 'credited total with only the unmetered turn token-priced' in log
print('Confirmed report-fixture assertion failure on unchanged parser.', flush=True)
