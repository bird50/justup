from datetime import datetime
from pathlib import Path
import secrets
from tempfile import TemporaryFile
from zipfile import ZipFile, ZIP_STORED

from flask import Flask, abort, redirect, render_template_string, request, send_file, session, url_for

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
IMAGE_TYPES = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
               '.gif': 'image/gif', '.webp': 'image/webp', '.avif': 'image/avif'}
BASE_FOLDER = Path(__file__).resolve().parent / 'uploads'

HTML = """
<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>JustUp · ไฟล์ของคุณ</title>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; padding: 32px 16px; font-family: sans-serif; background: #f4f7fb; color: #243248; }
    main { max-width: 860px; margin: auto; }
    h1 { margin-bottom: 8px; color: #0066cc; }
    .subtitle { color: #607086; margin-bottom: 28px; }
    .card { background: white; padding: 24px; border: 1px solid #dfe6ef; border-radius: 12px; margin-bottom: 20px; }
    h2 { font-size: 1.2rem; margin: 0 0 18px; }
    label { display: block; margin-bottom: 12px; }
    input[type=file] { max-width: 100%; }
    button { display: block; margin-top: 18px; padding: 12px 24px; background: #0066cc; color: white; border: 0; border-radius: 6px; font: inherit; cursor: pointer; }
    a { color: #005bb5; }
    a:focus-visible, summary:focus-visible, button:focus-visible { outline: 3px solid #edaa28; outline-offset: 3px; }
    .tree, .tree ul { list-style: none; padding-left: 20px; margin: 0; }
    .tree { padding-left: 0; }
    .tree ul { border-left: 1px solid #dfe6ef; margin-left: 8px; }
    summary { cursor: pointer; padding: 12px 4px; overflow-wrap: anywhere; }
    .file { display: flex; align-items: center; gap: 12px; padding: 12px 4px; border-bottom: 1px solid #eff2f6; }
    .name { flex: 1; min-width: 0; overflow-wrap: anywhere; }
    .size { font-size: .85rem; color: #607086; white-space: nowrap; }
    .download { padding: 7px 10px; border-radius: 5px; background: #edf5ff; text-decoration: none; white-space: nowrap; }
    .notice { background: #e9f7ee; padding: 14px; border-radius: 8px; }
    .thumbnail { width: 64px; height: 64px; object-fit: cover; border-radius: 6px; background: #edf1f6; }
    .folder-select { margin-right: 8px; }
    .preview-link { display: inline-flex; flex-shrink: 0; cursor: zoom-in; }
    dialog { width: min(960px, 94vw); max-height: 94vh; padding: 20px; border: 0; border-radius: 12px; }
    dialog::backdrop { background: rgb(0 0 0 / 75%); }
    .viewer-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
    .viewer-header h2 { margin: 0; overflow-wrap: anywhere; }
    .viewer-header button { margin: 0; flex-shrink: 0; }
    #full-image { display: block; max-width: 100%; max-height: 72vh; object-fit: contain; margin: auto; }
    .actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-bottom: 18px; }
    .actions button, .actions label { margin: 0; }
    .actions .delete { background: #b42318; }
    button:disabled { opacity: .45; cursor: default; }
    .empty { color: #607086; padding: 16px 0; }
    @media (max-width: 520px) { .card { padding: 16px; } .tree ul { padding-left: 12px; } .file { flex-wrap: wrap; gap: 8px; } .name { flex-basis: 100%; } .download { margin-left: auto; } }
  </style>
</head>
<body>
<main>
  <h1>📂 JustUp</h1>
  <p class="subtitle">อัปโหลดและดาวน์โหลดไฟล์ของคุณ จัดเก็บแยกตามวันที่</p>
  {% if uploaded %}<p class="notice" role="status">✔ อัปโหลดสำเร็จ {{ uploaded }} ไฟล์</p>{% endif %}
  {% if deleted %}<p class="notice" role="status">ลบแล้ว {{ deleted }} ไฟล์</p>{% endif %}
  <section class="card" aria-labelledby="upload-heading">
    <h2 id="upload-heading">อัปโหลดไฟล์</h2>
    <form method="post" enctype="multipart/form-data">
      <label for="files">เลือกไฟล์ได้หลายไฟล์พร้อมกัน</label>
      <input id="files" type="file" name="files" multiple required>
      <button type="submit">อัปโหลด</button>
    </form>
  </section>
  <section class="card" aria-labelledby="files-heading">
    <h2 id="files-heading">ไฟล์ที่อัปโหลดแล้ว</h2>
    {% macro branches(nodes, depth=0) %}
      {% for node in nodes %}
        {% if node.is_dir %}
          <li><details{% if depth > 0 %} open{% endif %}><summary><input class="folder-select" type="checkbox" aria-label="เลือกไฟล์ทั้งหมดในโฟลเดอร์ {{ node.name }}">📁 {{ node.name }}</summary><ul>{{ branches(node.children, depth + 1) }}</ul></details></li>
        {% else %}
          <li class="file">
            <input type="checkbox" name="selected" value="{{ node.path }}" aria-label="เลือก {{ node.name }}">
            {% if node.is_image %}<a class="preview-link" href="{{ url_for('preview_file', filename=node.path) }}" data-name="{{ node.name }}" aria-label="ดูภาพ {{ node.name }}"><img class="thumbnail" src="{{ url_for('preview_file', filename=node.path) }}" alt="ภาพตัวอย่าง {{ node.name }}" width="64" height="64" loading="lazy" decoding="async"></a>{% endif %}
            <span class="name">📄 {{ node.name }}</span>
            <span class="size">{{ node.size | filesizeformat }}</span>
            <a class="download" href="{{ url_for('download_file', filename=node.path) }}" download aria-label="ดาวน์โหลด {{ node.name }}">ดาวน์โหลด</a>
          </li>
        {% endif %}
      {% endfor %}
    {% endmacro %}
    {% if tree %}
    <form id="file-actions" method="post" action="{{ url_for('file_actions') }}">
      <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
      <div class="actions">
        <label><input id="select-all" type="checkbox"> เลือกทั้งหมด</label>
        <span id="selected-count" role="status">เลือก 0 ไฟล์</span>
        <button type="submit" name="action" value="download" disabled>ดาวน์โหลดที่เลือก (ZIP)</button>
        <button class="delete" type="submit" name="action" value="delete" disabled>ลบที่เลือก</button>
      </div>
      <ul class="tree">{{ branches(tree) }}</ul>
    </form>
    {% else %}<p class="empty">ยังไม่มีไฟล์ เริ่มต้นด้วยการอัปโหลดไฟล์ด้านบน</p>{% endif %}
  </section>
</main>
<dialog id="image-viewer" aria-labelledby="image-title">
  <div class="viewer-header"><h2 id="image-title">ดูภาพ</h2><button id="close-viewer" type="button" autofocus>ปิด</button></div>
  <img id="full-image" alt="">
  <p id="image-error" role="status" hidden>ไม่สามารถแสดงภาพนี้ได้</p>
</dialog>
<script>
  const form = document.getElementById('file-actions');
  if (form) {
    const boxes = [...form.querySelectorAll('input[name="selected"]')];
    const all = document.getElementById('select-all');
    const folders = [...form.querySelectorAll('.folder-select')];
    const descendants = folder => [...folder.closest('details').querySelectorAll('input[name="selected"]')];
    function update() {
      const count = boxes.filter(box => box.checked).length;
      document.getElementById('selected-count').textContent = `เลือก ${count} ไฟล์`;
      all.checked = count === boxes.length;
      all.indeterminate = count > 0 && count < boxes.length;
      form.querySelectorAll('button[type="submit"]').forEach(button => button.disabled = count === 0);
      folders.forEach(folder => {
        const children = descendants(folder);
        const selected = children.filter(box => box.checked).length;
        folder.checked = children.length > 0 && selected === children.length;
        folder.indeterminate = selected > 0 && selected < children.length;
        folder.disabled = children.length === 0;
      });
    }
    all.addEventListener('change', () => { boxes.forEach(box => box.checked = all.checked); update(); });
    boxes.forEach(box => box.addEventListener('change', update));
    folders.forEach(folder => {
      folder.addEventListener('click', event => event.stopPropagation());
      folder.addEventListener('change', () => {
        descendants(folder).forEach(box => box.checked = folder.checked);
        update();
      });
    });
    form.addEventListener('submit', event => {
      if (event.submitter?.value === 'delete' && !confirm(`ลบ ${boxes.filter(box => box.checked).length} ไฟล์ที่เลือกอย่างถาวร?`)) event.preventDefault();
    });
    update();
  }
  const viewer = document.getElementById('image-viewer');
  const fullImage = document.getElementById('full-image');
  const imageError = document.getElementById('image-error');
  fullImage.addEventListener('error', () => { imageError.hidden = false; });
  document.querySelectorAll('.preview-link').forEach(link => {
    link.addEventListener('click', event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      imageError.hidden = true;
      document.getElementById('image-title').textContent = link.dataset.name;
      fullImage.alt = link.dataset.name;
      fullImage.src = link.href;
      viewer.showModal();
    });
  });
  document.getElementById('close-viewer').addEventListener('click', () => viewer.close());
  viewer.addEventListener('click', event => {
    const rect = viewer.getBoundingClientRect();
    if (event.target === viewer && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) viewer.close();
  });
</script>
</body>
</html>
"""


def upload_root():
    return Path(BASE_FOLDER).resolve()


def file_tree(folder, root):
    nodes = []
    if not folder.exists():
        return nodes
    entries = list(folder.iterdir())
    directories = sorted((p for p in entries if p.is_dir()), key=lambda p: p.name.casefold(), reverse=True)
    files = sorted((p for p in entries if not p.is_dir()), key=lambda p: p.name.casefold())
    for entry in directories + files:
        # Do not expose linked files or recurse into linked directories.
        if entry.is_symlink():
            continue
        if entry.is_dir():
            nodes.append(dict(name=entry.name, is_dir=True, children=file_tree(entry, root)))
        elif entry.is_file():
            nodes.append(dict(name=entry.name, is_dir=False,
                              path=entry.relative_to(root).as_posix(), size=entry.stat().st_size,
                              is_image=entry.suffix.lower() in IMAGE_TYPES))
    return nodes


@app.route('/', methods=['GET', 'POST'])
def upload_file():
    root = upload_root()
    if request.method == 'POST':
        uploaded_files = [f for f in request.files.getlist('files') if f.filename]
        if not uploaded_files:
            abort(400, description='กรุณาเลือกไฟล์ที่ต้องการอัปโหลด')
        now = datetime.now()
        folder = root / now.strftime('%Y-%m') / now.strftime('%d')
        if not folder.resolve().is_relative_to(root):
            abort(400)
        folder.mkdir(parents=True, exist_ok=True)
        for f in uploaded_files:
            # Preserve Unicode filenames while removing client-supplied path components.
            name = f.filename.replace('\\', '/').rsplit('/', 1)[-1]
            if name in ('', '.', '..') or '\x00' in name:
                abort(400, description='ชื่อไฟล์ไม่ถูกต้อง')
            target = folder / name
            suffix = 0
            while True:
                try:
                    # Exclusive creation prevents overwrites, including existing symlinks.
                    with target.open('xb') as destination:
                        f.save(destination)
                    break
                except FileExistsError:
                    suffix += 1
                    target = folder / f'{Path(name).stem} ({suffix}){Path(name).suffix}'
        return redirect(url_for('upload_file', uploaded=len(uploaded_files)), code=303)
    session.setdefault("csrf_token", secrets.token_hex(32))
    return render_template_string(HTML, tree=file_tree(root, root),
                                  csrf_token=session["csrf_token"],
                                  deleted=max(0, request.args.get("deleted", 0, type=int)),
                                  uploaded=max(0, request.args.get('uploaded', 0, type=int)))


def resolve_file(filename):
    root = upload_root()
    candidate = root / filename
    if '..' in Path(filename).parts:
        abort(404)
    if any(part.is_symlink() for part in (candidate, *candidate.parents) if part != root and root in part.parents):
        abort(404)
    target = candidate.resolve()
    if not target.is_relative_to(root) or not target.is_file():
        abort(404)
    return target


@app.get('/download/<path:filename>')
def download_file(filename):
    target = resolve_file(filename)
    return send_file(target, as_attachment=True, download_name=target.name)


@app.get('/preview/<path:filename>')
def preview_file(filename):
    target = resolve_file(filename)
    mimetype = IMAGE_TYPES.get(target.suffix.lower())
    if not mimetype:
        abort(404)
    response = send_file(target, mimetype=mimetype)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "default-src 'none'; sandbox"
    return response


@app.post('/file-actions')
def file_actions():
    token = session.get('csrf_token')
    if not token or not secrets.compare_digest(token, request.form.get('csrf_token', '')):
        abort(400, description='กรุณาโหลดหน้าใหม่แล้วลองอีกครั้ง')
    action = request.form.get('action')
    selected = list(dict.fromkeys(request.form.getlist('selected')))
    if action not in ('delete', 'download') or not selected:
        abort(400, description='กรุณาเลือกไฟล์และคำสั่ง')
    # Validate the complete selection before modifying any files.
    targets = [resolve_file(name) for name in selected]
    if action == 'delete':
        for target in targets:
            target.unlink()
        return redirect(url_for('upload_file', deleted=len(targets)), code=303)
    archive = TemporaryFile()
    try:
        with ZipFile(archive, 'w', compression=ZIP_STORED) as bundle:
            for target in targets:
                bundle.write(target, arcname=target.relative_to(upload_root()).as_posix())
        archive.seek(0)
        response = send_file(archive, mimetype='application/zip', as_attachment=True,
                             download_name='justup-selected.zip')
        response.call_on_close(archive.close)
        return response
    except Exception:
        archive.close()
        raise


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
