"""Optional REA 4.0.1 packaged ground truth, never a Claude/artifact wrapper.

Requires an explicitly supplied preinstalled isolated npm prefix. Installs nothing.
Raw outputs/fixtures stay in a newly owned TEMP directory; environment redirection
is not a security sandbox. Target JavaScript is inspected, never invoked here.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

LIMIT = 8 * 1024 * 1024
HERE = Path(__file__).resolve().parent


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def run(node, cli, args, root, env, name):
    start = time.monotonic()
    output, errors = root / (name + '.json'), root / (name + '.stderr')
    with output.open('xb') as stdout, errors.open('xb') as stderr:
        child = subprocess.Popen([node, str(cli), *args], cwd=root, env=env, stdout=stdout, stderr=stderr)
        try:
            code = child.wait(timeout=60)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
            raise RuntimeError('REA_TIMEOUT') from None
    if code != 0 or output.stat().st_size > LIMIT:
        raise RuntimeError('REA_EXIT_OR_OUTPUT_LIMIT')
    obj = json.loads(output.read_bytes())
    if obj.get('ok') is not True:
        raise RuntimeError('REA_TYPED_FAILURE')
    return obj['data'], round((time.monotonic() - start) * 1000)


def smoke(tool_root, node):
    tool_root = tool_root.resolve(strict=True)
    package = tool_root / 'node_modules' / 'rea-agents'
    if json.loads((package / 'package.json').read_bytes())['version'] != '4.0.1':
        raise RuntimeError('REA_PIN_MISMATCH')
    root = Path(tempfile.mkdtemp(prefix='rea-package-smoke-'))
    # Retained private raw evidence is intentional; cleanup is an explicit later action.
    home = root / 'home'
    env = {key: os.environ[key] for key in ('PATH', 'SystemRoot', 'WINDIR', 'COMSPEC', 'PATHEXT', 'SystemDrive')
           if key in os.environ}
    for key in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP'):
        path = home / key
        path.mkdir(parents=True)
        env[key] = str(path)
    recipe = json.loads((HERE / 'fixtures' / 'rea' / 'package-recipe.json').read_bytes())
    cli = package / 'scripts' / 'rea.mjs'
    builder = tool_root / 'node_modules' / '@electron' / 'asar' / 'lib' / 'asar.js'
    build_code = "const asar = await import(process.argv[1]); await asar.createPackage(process.argv[2],process.argv[3]);"
    analyses, inventories, runs = {}, {}, {}
    for label in ('old', 'new'):
        folder = root / label
        folder.mkdir()
        version = recipe['versions'][label]
        for name, source in version['files'].items():
            if Path(name).name != name or not name or name in ('.', '..'):
                raise RuntimeError('RECIPE_PATH_REFUSED')
            raw = source['text'].encode('utf-8')
            if digest(raw) != source['sha256']:
                raise RuntimeError('RECIPE_HASH_MISMATCH')
            (folder / name).write_bytes(raw)
        archive = root / (label + '.asar')
        built = subprocess.run([node, '--input-type=module', '-e', build_code, builder.as_uri(),
                                str(folder), str(archive)], cwd=root, env=env, capture_output=True, timeout=30)
        if built.returncode != 0 or digest(archive.read_bytes()) != version['asar_sha256']:
            raise RuntimeError('ASAR_BUILD_MISMATCH')
        analysis, duration = run(node, cli, ['analyze-javascript-application', str(archive),
            '--artifact-format', 'asar', '--format', 'json', '--full-output'], root, env, label + '-analysis')
        if analysis['subject']['digest']['sha256'] != version['asar_sha256']:
            raise RuntimeError('REA_ARTIFACT_IDENTITY_MISMATCH')
        analyses[label] = analysis
        runs[label] = duration
        inspected, _ = run(node, cli, ['inspect-artifact', str(archive), '--format', 'json', '--full-output'],
                           root, env, label + '-inspection')
        inventory = inspected['normalized_result']['substeps'][0]['evidence']['normalized_result']
        nodes = {item['artifact_id']: item for item in inventory['nodes']}
        observed = {item['logical_path']: nodes[item['artifact_id']]['sha256'] for item in inventory['occurrences']
                    if item['logical_path'] != '.'}
        if observed != {name: source['sha256'] for name, source in version['files'].items()}:
            raise RuntimeError('REA_RESOURCE_HASH_MISMATCH')
        inventories[label] = inspected['evidence_id']
    comparison_input = root / 'comparison-input.json'
    comparison_input.write_text(json.dumps({'left': analyses['old'], 'right': analyses['new']}), encoding='utf-8')
    compared, _ = run(node, cli, ['compare-application-versions', str(comparison_input), '--format', 'json',
                                '--full-output'], root, env, 'version-comparison')
    names = {node['node_id']: [observation['label'] for observation in node['observations']]
             for data in analyses.values() for node in data['normalized_result']['graph']['nodes']}
    changed = [item for item in compared['normalized_result']['items'] if item['status'] == 'changed'
               and names.get(item.get('left_node_id')) == ['main.cjs']
               and names.get(item.get('right_node_id')) == ['main.cjs']]
    if len(changed) != 2 or any((root / label / 'EXECUTION_FORBIDDEN').exists() for label in ('old', 'new')):
        raise RuntimeError('DELTA_OR_SENTINEL_CHECK_FAILED')
    result = {'schema': 1, 'status': 'PACKAGED_SMOKE_CORRECT', 'adoption': 'EXPERIMENTAL',
              'rea_version': '4.0.1', 'analysis_duration_ms': runs,
              'evidence_refs': [data['evidence_id'] for data in analyses.values()] + list(inventories.values()) +
                               [compared['evidence_id']],
              'graph_summary': compared['normalized_result']['summary'],
              'native_elf': 'NOT_RUN', 'native_pe': 'NOT_RUN', 'claude_pair': 'NOT_RUN',
              'runtime': 'NOT_RUN', 'raw_evidence': str(root)}
    (root / 'receipt.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tool-root', type=Path, required=True)
    parser.add_argument('--node', default='node')
    args = parser.parse_args()
    try:
        result = smoke(args.tool_root, args.node)
        private = HERE.parent / 'docs' / ('rea-reproduction-' + Path(result['raw_evidence']).name + '.local.md')
        with private.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
        result.pop('raw_evidence')
        print(json.dumps(result))
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
        code = str(error) if isinstance(error, RuntimeError) else 'REA_INPUT_OR_IO_REFUSED'
        print(json.dumps({'status': 'REFUSED', 'reason': code}))
        raise SystemExit(2)
