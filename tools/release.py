#!/usr/bin/env python3
"""Build/validate the allowlisted upgrade ZIP without touching deployed services."""
import argparse
import hashlib
import io
import json
import re
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
NAME = 'Flow-v3.4-Learning-Reliability-Upgrade.zip'
STAMP = (1980, 1, 1, 0, 0, 0)
MANIFEST = 'release-manifest.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_name(name):
    p = PurePosixPath(name)
    private = {'data', 'backups', 'recordings', 'uploads', 'logs', '.git', '.venv', '__pycache__', 'node_modules'}
    lower = name.lower()
    if (p.is_absolute() or '..' in p.parts or '\\' in name or str(p) != name
            or any(part.lower() in private for part in p.parts)
            or any(part.startswith('.') for part in p.parts)
            or any(word in lower for word in ('credentials', 'service-account', 'adc.json'))
            or re.search(r'\.(?:sqlite\w*|db(?:-.*)?|pem|key|log|zip|webm|wav|mp3|mp4)$', lower)
            or ('.env' in lower and name != 'flow/flow.env.example')):
        raise ValueError('Unsafe release path: ' + name)


def source_files(root):
    names = (root / 'tools/release-files.txt').read_text().splitlines()
    if len(names) != len(set(names)):
        raise ValueError('Duplicate allowlist path')
    files = {}
    for name in sorted(names):
        safe_name(name)
        path = root / name
        if any((root / Path(*PurePosixPath(name).parts[:i])).is_symlink()
               for i in range(1, len(PurePosixPath(name).parts) + 1)):
            raise ValueError('Symlinks are not release inputs: ' + name)
        files[name] = path.read_bytes()
    check_requirements(files)
    return files


def check_requirements(files):
    # Cover every explicit source operand and both website install loops.
    for directory, variable in [('flow', 'FLOW_SOURCE_DIR'), ('flow-gateway', 'flow_source')]:
        script = files[directory + '/upgrade.sh'].decode()
        required = re.findall(r'\$' + variable + r'/([\w./-]+)', script)
        if directory == 'flow':
            lists = re.findall(r'for name in ([^;]+); do', script)
            if len(lists) != 2:
                raise ValueError('Website upgrade file-list format changed; review packaging')
            required += lists[0].split() + ['public/' + x for x in lists[1].split()]
        for name in required:
            if name.endswith('/') or name == 'tests/':
                continue
            if directory + '/' + name not in files:
                raise ValueError('Missing upgrade input: ' + directory + '/' + name)
    page = files['flow/public/index.html'].decode()
    for asset in re.findall(r'(?:src|href)="/([^"?]+)', page):
        if 'flow/public/' + asset not in files:
            raise ValueError('Missing frontend asset: ' + asset)
    if not any(n.startswith('flow/tests/') for n in files):
        raise ValueError('Missing website tests')
    if 'flow-gateway/tests/test_gateway.py' not in files:
        raise ValueError('Missing gateway tests')


def archive_bytes(root):
    files = source_files(root)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    files[MANIFEST] = (json.dumps({
        'website_version': '3.4', 'gateway_version': '2.2', 'source_commit': commit,
        'production_deployment': 'unverified', 'real_gemini_connectivity': 'unverified',
        'sha256': {n: digest(b) for n, b in files.items()},
    }, sort_keys=True, indent=2) + '\n').encode()
    output = io.BytesIO()
    # Stored entries avoid compressor/version-dependent output. All metadata is fixed.
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, STAMP)
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | (0o755 if name.endswith('.sh') else 0o644)) << 16
            archive.writestr(info, data)
    return output.getvalue()


def validate(path, root):
    expected = archive_bytes(root)
    actual = path.read_bytes()
    if actual != expected:
        raise ValueError('Archive differs from the reproducible allowlisted source package')
    with zipfile.ZipFile(io.BytesIO(actual)) as archive:
        if archive.testzip():
            raise ValueError('Archive CRC failure')
        check_requirements({n: archive.read(n) for n in archive.namelist()})
        # Extract only after exact membership, paths, hashes and metadata were checked.
        with tempfile.TemporaryDirectory() as tmp:
            archive.extractall(tmp)
            subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_package.py', '-v'],
                           cwd=Path(tmp) / 'flow', check=True)
            for name in ('gateway.py', 'audio_validation.py', 'nginx_update.py'):
                compile((Path(tmp) / 'flow-gateway' / name).read_bytes(), name, 'exec')
    return digest(actual)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'validate', 'check'])
    parser.add_argument('--output', type=Path, default=ROOT / 'dist' / NAME)
    args = parser.parse_args()
    if args.command in ('build', 'check'):
        first = archive_bytes(ROOT)
        if first != archive_bytes(ROOT):
            raise ValueError('Build is not reproducible')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(first)
    checksum = validate(args.output, ROOT)
    args.output.with_suffix(args.output.suffix + '.sha256').write_text(checksum + '  ' + args.output.name + '\n')
    print('Validated reproducible upgrade archive: ' + str(args.output))
    print('SHA256: ' + checksum)
    print('Production deployment and real Gemini connectivity: UNVERIFIED')


if __name__ == '__main__':
    main()
