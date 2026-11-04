"""Build a strictly allowlisted static site: no private data, configs or backend."""
import argparse
import base64
import hashlib
import io
import json
import shutil
import tarfile
from pathlib import Path, PurePosixPath
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
FILES = ['index.html', 'app.js', 'ai.js', 'store.js', 'library.js', 'retrieval.js', 'pdf.js', 'browser.css', 'manifest.webmanifest']
SHARED = ['cornell.js', 'knowledge.js', 'styles.css', 'favicon.svg']


def build(output):
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents and output.parts[-1] in {'browser', 'data', '.local'}:
        raise ValueError('Choose a separate build-output directory')
    if output.exists():
        if not (output / '.study-atlas-browser-build').is_file():
            raise ValueError('Refusing to replace a directory that is not a previous browser build')
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / '.study-atlas-browser-build').write_text('Static public code only.\n')
    for name in FILES:
        shutil.copy2(ROOT / 'browser' / name, output / name)
    (output / 'shared').mkdir()
    for name in SHARED:
        shutil.copy2(ROOT / name, output / 'shared' / name)
    (output / '.nojekyll').touch()
    (output / 'PROJECT-LICENSE.txt').write_text((ROOT / 'LICENSE').read_text())
    (output / 'LEGACY-MIT-LICENSE.txt').write_text((ROOT / 'LICENSE-MIT-LEGACY').read_text())
    lock = json.loads((ROOT / 'browser/vendor.lock.json').read_text())['pdfjs-dist']
    with urlopen(lock['url'], timeout=60) as response:
        package = response.read(80 * 1024 * 1024 + 1)
    if len(package) > 80 * 1024 * 1024:
        raise ValueError('PDF dependency package too large')
    actual = 'sha512-' + base64.b64encode(hashlib.sha512(package).digest()).decode()
    if actual != lock['integrity']:
        raise ValueError('PDF dependency integrity mismatch')
    target = output / 'vendor/pdfjs'
    target.mkdir(parents=True)
    names = []
    with tarfile.open(fileobj=io.BytesIO(package), mode='r:gz') as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            path = PurePosixPath(member.name)
            relative = None
            if path.parent == PurePosixPath('package/legacy/build') and path.suffix == '.mjs':
                relative = PurePosixPath(path.name)
            elif any(path.is_relative_to('package/' + part) for part in ['cmaps', 'standard_fonts', 'wasm']):
                relative = path.relative_to('package')
            elif member.name in {'package/LICENSE', 'package/NOTICE'}:
                relative = PurePosixPath(path.name)
            if relative is None:
                continue
            if '..' in relative.parts or relative.is_absolute() or member.size > 20 * 1024 * 1024:
                raise ValueError('Unexpected dependency member')
            dest = target.joinpath(*relative.parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(archive.extractfile(member).read())
            names.append(str(relative))
    for required in ['pdf.mjs', 'pdf.worker.mjs', 'LICENSE']:
        if required not in names:
            raise ValueError('Missing PDF runtime: ' + required)
    (output / 'THIRD_PARTY.txt').write_text('PDF.js / pdfjs-dist ' + lock['version'] + '\nMozilla Foundation and contributors\nApache License 2.0: vendor/pdfjs/LICENSE\nhttps://github.com/mozilla/pdf.js\n')
    (output / 'build-info.json').write_text(json.dumps({'application': 'study-atlas-browser', 'pdfjs': lock['version'], 'privateDataIncluded': False}))
    files = [p for p in output.rglob('*') if p.is_file()]
    print(json.dumps({'files': len(files), 'bytes': sum(p.stat().st_size for p in files), 'privateFilesIncluded': 0, 'output': str(output)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(ROOT / '_site-browser'))
    build(parser.parse_args().output)
