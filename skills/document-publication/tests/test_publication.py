import contextlib
import functools
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import publication
import publish_document
from install import install_link, migrate
from reader_service import ReaderHandler


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / 'state'
        self.source = self.root / 'research' / 'decision.md'
        self.source.parent.mkdir()
        self.source.write_text('# Decision report\n\nFirst revision.\n')
        self.state.mkdir()
        publication.save_json(self.state / 'registry.json', {'version': 1, 'origin': 'https://machine.example.ts.net',
                                                            'refresh_seconds': 30, 'documents': []})

    def html(self, entry):
        return (self.state / 'site' / entry['path']).read_text()

    def test_snapshot_stable_url_and_explicit_republication(self):
        first = publication.register(self.state, self.source)
        self.source.write_text('# Decision report\n\nSecond revision.\n')
        publication.generate(self.state)
        self.assertIn('First revision.', self.html(first))
        self.assertNotIn('Second revision.', self.html(first))
        second = publication.register(self.state, self.source)
        self.assertEqual(first['url'], second['url'])
        self.assertIn('Second revision.', self.html(second))
        self.assertEqual(len(publication.read_registry(self.state)['documents']), 1)

    def test_live_refresh_and_mode_transition(self):
        entry = publication.register(self.state, self.source, 'live')
        self.source.write_text('# Decision report\n\nUpdated source.\n')
        publication.generate(self.state)
        self.assertIn('Updated source.', self.html(entry))
        repeated = publication.register(self.state, self.source)
        self.assertEqual(repeated['mode'], 'live')
        snapshot = publication.register(self.state, self.source, 'snapshot')
        self.assertEqual(entry['url'], snapshot['url'])
        self.source.write_text('# Changed after snapshot\n')
        publication.generate(self.state)
        self.assertIn('Updated source.', self.html(entry))

    def test_exact_file_selection_and_link_rewriting(self):
        neighbor = self.source.with_name('private.md')
        neighbor.write_text('# Private neighbor\n\nUnpublished material.\n')
        self.source.write_text('# Selected report\n\n[Neighbor](private.md)\n\n<script>attack()</script>\n')
        first = publication.register(self.state, self.source)
        self.assertNotIn('<script>', self.html(first))
        self.assertIn('local-reference', self.html(first))
        self.assertEqual(len(publication.read_registry(self.state)['documents']), 1)
        self.assertNotIn('Unpublished material.', (self.state / 'site/index.html').read_text())
        other = publication.register(self.state, neighbor)
        self.assertIn('/reader/' + other['path'], self.html(first))

    def test_missing_live_source_retains_page_and_discloses_staleness(self):
        entry = publication.register(self.state, self.source, 'live')
        self.source.unlink()
        results = publication.generate(self.state)
        self.assertIn('error', results[entry['id']])
        self.assertIn('First revision.', self.html(entry))
        self.assertIn('Source unavailable', self.html(entry))
        self.assertIn('Source unavailable', (self.state / 'site/index.html').read_text())
        self.source.write_text('# Restored source\n')
        results = publication.generate(self.state)
        self.assertNotIn('error', results[entry['id']])
        self.assertNotIn('Source unavailable', self.html(entry))

    def test_invalid_files_are_rejected_without_registration(self):
        for name, content in [('binary.md', b'\xff'), ('null.md', b'# Text\0hidden'), ('file.txt', b'text')]:
            path = self.root / name
            path.write_bytes(content)
            with self.assertRaises((ValueError, UnicodeError)):
                publication.register(self.state, path)
        with self.assertRaises((OSError, ValueError)):
            publication.register(self.state, self.root / 'missing.md')
        with self.assertRaises(ValueError):
            publication.register(self.state, self.source.parent)
        self.assertEqual(publication.read_registry(self.state)['documents'], [])

    def test_remove_withdraws_output_and_preserves_source(self):
        entry = publication.register(self.state, self.source)
        publication.remove(self.state, entry['id'])
        self.assertFalse((self.state / 'site' / entry['path']).exists())
        self.assertFalse((self.state / 'snapshots' / (entry['id'] + '.md')).exists())
        self.assertTrue(self.source.exists())
        self.assertNotIn(entry['title'], (self.state / 'site/index.html').read_text())

    def test_concurrent_processes_preserve_all_registrations(self):
        processes = []
        code = 'from pathlib import Path; import sys; sys.path.insert(0,sys.argv[1]); from publication import register; register(Path(sys.argv[2]),sys.argv[3])'
        for index in range(5):
            path = self.root / f'report-{index}.md'
            path.write_text(f'# Report {index}\n')
            processes.append(subprocess.Popen([sys.executable, '-c', code, str(SCRIPTS), str(self.state), str(path)],
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        for process in processes:
            out, error = process.communicate(timeout=20)
            self.assertEqual(process.returncode, 0, error.decode())
        self.assertEqual(len(publication.read_registry(self.state)['documents']), 5)

    def test_legacy_migration_preserves_report_url_and_body(self):
        self.state.joinpath('registry.json').unlink()
        legacy_path = 'existing-collection/decision.html'
        publication.save_json(self.state / 'manifest.json', [{'source': str(self.source), 'url': '/reader/' + legacy_path, 'title': 'Decision report'}])
        publication.atomic_write(self.state / 'site/existing-collection/index.html', '<title>Existing collection · Research reader</title>')
        migrate(self.state, 'https://machine.example.ts.net')
        publication.generate(self.state)
        registry = publication.read_registry(self.state)
        self.assertEqual(registry['documents'][0]['path'], legacy_path)
        self.assertEqual(registry['documents'][0]['collection_title'], 'Existing collection')
        self.assertIn('First revision.', (self.state / 'site' / legacy_path).read_text())

    def test_registry_rejects_path_traversal(self):
        entry = publication.register(self.state, self.source)
        registry = publication.read_registry(self.state)
        registry['documents'][0]['path'] = '../escape.html'
        publication.save_json(self.state / 'registry.json', registry)
        with self.assertRaises(ValueError):
            publication.generate(self.state)

    def test_installation_links_are_idempotent_and_preserve_existing_files(self):
        destination = self.root / 'bin' / 'publish-document'
        install_link(self.source, destination)
        install_link(self.source, destination)
        self.assertEqual(destination.resolve(), self.source.resolve())
        unrelated = self.root / 'existing-command'
        unrelated.write_text('existing installation')
        with self.assertRaises(ValueError):
            install_link(self.source, unrelated)
        self.assertEqual(unrelated.read_text(), 'existing installation')

    def test_transport_refuses_funnel_and_missing_route(self):
        private = {'TCP': {'443': {'HTTPS': True}}, 'Web': {'machine.example.ts.net:443': {'Handlers': {'/reader': {'Proxy': 'http://127.0.0.1:8767'}}}}}
        with patch('publication.subprocess.run') as run:
            run.return_value.stdout = json.dumps(private)
            self.assertEqual(publication.transport_origin(), 'https://machine.example.ts.net')
            private['AllowFunnel'] = {'machine.example.ts.net:443': True}
            run.return_value.stdout = json.dumps(private)
            with self.assertRaises(ValueError):
                publication.transport_origin()
            run.return_value.stdout = '{}'
            with self.assertRaises(ValueError):
                publication.transport_origin()

    def test_cli_verification_failure_returns_no_success_link(self):
        output, error = io.StringIO(), io.StringIO()
        with patch.dict('os.environ', {'DOCUMENT_PUBLICATION_STATE': str(self.state)}), \
                patch.object(sys, 'argv', ['publish-document', str(self.source)]), \
                patch('publish_document.transport_origin', return_value='https://machine.example.ts.net'), \
                patch('publish_document.verify', side_effect=ValueError('wrong content')), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            self.assertEqual(publish_document.main(), 1)
        self.assertEqual(output.getvalue(), '')
        self.assertIn('No verified link', error.getvalue())
        self.assertEqual(len(publication.read_registry(self.state)['documents']), 1)

    def test_http_delivery_hash_and_unpublished_paths(self):
        entry = publication.register(self.state, self.source)
        server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(ReaderHandler, directory=str(self.state / 'site')))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}/reader/'
            self.assertTrue(publication.verify(base + entry['path'], entry['html_sha256']))
            with self.assertRaises(ValueError):
                publication.verify(base + entry['path'], 'incorrect hash')
            for path in ('registry.json', 'snapshots/' + entry['id'] + '.md', '../registry.json', '%2e%2e/registry.json', 'unpublished/'):
                with self.assertRaises(HTTPError) as error:
                    urlopen(base + path, timeout=5)
                self.assertEqual(error.exception.code, 404)
                error.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
