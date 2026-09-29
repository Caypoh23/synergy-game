"""Verify that the deployable game is self-contained and has no local references."""
from html.parser import HTMLParser
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
page = root / 'docs/index.html'
text = page.read_text(encoding='utf-8')

class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.external = []
        self.has_main = False
    def handle_starttag(self, tag, attrs):
        self.has_main |= tag == 'main'
        for key, value in attrs:
            if key in ('src', 'href', 'action') and value and not value.startswith(('data:', '#')):
                self.external.append((tag, key, value))

parser = References()
parser.feed(text)
assert parser.has_main, 'Missing game entry point'
assert not parser.external, f'Unexpected external dependency: {parser.external}'
assert '<meta name="viewport"' in text, 'Missing mobile viewport'
assert not re.search(r'/Users/|/var/folders/|gh[pousr]_[A-Za-z0-9]{20,}|sk-proj-', text), 'Unexpected local path or credential marker'
assert (root / 'docs/.nojekyll').exists(), 'Missing static-site marker'
print(f'OK: self-contained game, {page.stat().st_size:,} bytes')
