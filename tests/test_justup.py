import io
import tempfile
import unittest
from zipfile import ZipFile
from pathlib import Path
from urllib.parse import quote

import justup


class FileBrowserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = justup.BASE_FOLDER
        justup.BASE_FOLDER = Path(self.temp.name) / 'uploads'
        self.root = justup.BASE_FOLDER
        self.client = justup.app.test_client()

    def tearDown(self):
        justup.BASE_FOLDER = self.original
        self.temp.cleanup()

    def upload(self, name, content=b'example'):
        return self.client.post('/', data={'files': (io.BytesIO(content), name)})

    def action(self, action, selected, token=True):
        self.client.get('/')
        with self.client.session_transaction() as state:
            csrf = state['csrf_token']
        return self.client.post('/file-actions', data={
            'action': action, 'selected': selected, 'csrf_token': csrf if token else 'invalid'})

    def test_latest_folders_collapsed_and_image_preview(self):
        for month in ('2025-09', '2026-10'):
            folder = self.root / month / '16'
            folder.mkdir(parents=True)
            (folder / 'photo.png').write_bytes(b'\x89PNG\r\n\x1a\n')
        page = self.client.get('/').get_data(as_text=True)
        self.assertLess(page.index('2026-10'), page.index('2025-09'))
        self.assertIn('<details><summary><input class="folder-select" type="checkbox" aria-label="เลือกไฟล์ทั้งหมดในโฟลเดอร์ 2026-10"', page)
        self.assertIn('class="thumbnail"', page)
        response = self.client.get('/preview/2026-10/16/photo.png')
        self.assertEqual(response.mimetype, 'image/png')
        self.assertEqual(response.data, b'\x89PNG\r\n\x1a\n')
        response.close()
        (self.root / 'unsafe.svg').write_text('<svg></svg>')
        self.assertEqual(self.client.get('/preview/unsafe.svg').status_code, 404)
        self.assertEqual(self.client.get('/preview/../secret.png').status_code, 404)

    def test_selected_zip_and_delete(self):
        for day in ('01', '02'):
            folder = self.root / '2026-10' / day
            folder.mkdir(parents=True)
            (folder / 'ภาพ.txt').write_text(day)
        selected = ['2026-10/01/ภาพ.txt', '2026-10/02/ภาพ.txt']
        response = self.action('download', selected)
        self.assertEqual(response.status_code, 200)
        with ZipFile(io.BytesIO(response.data)) as archive:
            self.assertEqual(archive.namelist(), selected)
            self.assertEqual(archive.read(selected[1]), b'02')
        response.close()
        self.assertEqual(self.action('delete', selected, token=False).status_code, 400)
        self.assertEqual(self.action('delete', [selected[0], '../outside.txt']).status_code, 404)
        self.assertTrue((self.root / selected[0]).exists())
        self.assertEqual(self.action('download', []).status_code, 400)
        response = self.action('delete', [selected[0], selected[0]])
        self.assertEqual(response.status_code, 303)
        self.assertFalse((self.root / selected[0]).exists())
        self.assertTrue((self.root / selected[1]).exists())

    def test_empty_and_nested_tree_download(self):
        self.assertIn('ยังไม่มีไฟล์', self.client.get('/').get_data(as_text=True))
        folder = self.root / '2025-09' / '10'
        folder.mkdir(parents=True)
        name = 'รายงาน #1.pdf'
        (folder / name).write_bytes(b'pdf-example')
        page = self.client.get('/').get_data(as_text=True)
        self.assertIn('<details open>', page)
        self.assertIn(name, page)
        self.assertIn('2025-09', page)
        response = self.client.get('/download/' + quote('2025-09/10/' + name))
        self.assertEqual(response.data, b'pdf-example')
        self.assertIn('attachment;', response.headers['Content-Disposition'])
        response.close()

    def test_upload_redirect_and_duplicate_preservation(self):
        first = self.upload('ภาพ.txt', b'first')
        self.assertEqual(first.status_code, 303)
        self.assertIn('อัปโหลดสำเร็จ 1 ไฟล์', self.client.get(first.location).get_data(as_text=True))
        self.upload('ภาพ.txt', b'second')
        self.assertEqual(next(self.root.rglob('ภาพ.txt')).read_bytes(), b'first')
        self.assertEqual(next(self.root.rglob('ภาพ (1).txt')).read_bytes(), b'second')

    def test_escape_html_and_strip_upload_paths(self):
        self.upload('../../../outside.txt')
        self.assertFalse((Path(self.temp.name) / 'outside.txt').exists())
        self.assertEqual(len(list(self.root.rglob('outside.txt'))), 1)
        self.upload('<img src=x onerror=alert(1)>.txt')
        page = self.client.get('/').get_data(as_text=True)
        self.assertNotIn('<img src=x', page)
        self.assertIn('&lt;img', page)

    def test_block_traversal_missing_files_and_symlinks(self):
        self.root.mkdir()
        outside = Path(self.temp.name) / 'secret.txt'
        outside.write_text('private')
        (self.root / 'linked.txt').symlink_to(outside)
        (self.root / 'linked-dir').symlink_to(Path(self.temp.name), target_is_directory=True)
        for path in ('../secret.txt', '%2e%2e/secret.txt', 'linked.txt', 'linked-dir/secret.txt', 'missing.txt'):
            self.assertEqual(self.client.get('/download/' + path).status_code, 404, path)
        page = self.client.get('/').get_data(as_text=True)
        self.assertNotIn('linked.txt', page)
        self.assertNotIn('linked-dir', page)
        self.assertEqual(self.client.post('/').status_code, 400)


if __name__ == '__main__':
    unittest.main()
