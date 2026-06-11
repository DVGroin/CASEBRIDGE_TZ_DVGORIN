import os, sys, re, json, zipfile, tempfile, shutil
from datetime import datetime
from flask import Flask, render_template_string, request, send_file, redirect, jsonify
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

UPLOAD_DIR = tempfile.mkdtemp(prefix='casebridge_uploads_')

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Генератор ТЗ — CaseBridge</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background: #0a0c10; color: #e5e7eb; line-height: 1.5;
            min-height: 100vh; display: flex; flex-direction: column;
            align-items: center; justify-content: center; padding: 20px;
        }
        .container {
            max-width: 800px; width: 100%; background: #111827;
            border-radius: 1.5rem; padding: 2.5rem 2rem;
            box-shadow: 0 20px 30px -10px rgba(0,0,0,0.6);
            border: 1px solid #1f2937;
        }
        h1 { font-size: 2rem; font-weight: 600; margin-bottom: 0.25rem; color: #f9fafb; }
        .subtitle { color: #9ca3af; margin-bottom: 2rem; font-size: 0.95rem; }
        .form-section { margin-bottom: 2rem; }
        .form-section h2 { font-size: 1.25rem; font-weight: 600; margin-bottom: 1rem; color: #e5e7eb; }
        label { font-weight: 500; font-size: 0.9rem; display: block; margin-bottom: 0.5rem; color: #cbd5e1; }
        .optional { font-weight: 400; color: #9ca3af; font-size: 0.8rem; margin-left: 0.5rem; }
        input[type="text"], input[type="url"], input[type="email"], input[type="tel"],
        textarea, select {
            width: 100%; padding: 0.75rem 1rem; background: #1f2937;
            border: 1px solid #374151; border-radius: 0.75rem;
            font-size: 0.95rem; color: #e5e7eb; transition: border-color 0.2s, box-shadow 0.2s;
        }
        input:focus, textarea:focus, select:focus {
            outline: none; border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,0.2);
        }
        .radio-group { display: flex; flex-wrap: wrap; gap: 0.75rem; }
        .radio-group label {
            display: flex; align-items: center; gap: 0.5rem; background: #1f2937;
            padding: 0.6rem 1rem; border-radius: 0.75rem; font-weight: 500;
            cursor: pointer; border: 1px solid #374151; transition: 0.15s;
        }
        .radio-group label:hover { border-color: #3b82f6; background: #1e293b; }
        .radio-group input[type="radio"] { accent-color: #3b82f6; }
        .conditional { display: none; margin-top: 1rem; }
        .conditional.active { display: block; }
        details.hidden-panel {
            margin-top: 2rem; border-top: 1px solid #1f2937; padding-top: 1.5rem;
        }
        details.hidden-panel summary {
            font-weight: 600; font-size: 0.95rem; cursor: pointer; list-style: none;
            display: flex; align-items: center; gap: 0.5rem; color: #3b82f6; user-select: none;
        }
        details.hidden-panel summary::after {
            content: '▼'; font-size: 0.8rem; margin-left: auto;
            transition: transform 0.2s; color: #6b7280;
        }
        details.hidden-panel[open] summary::after { transform: rotate(180deg); }
        .btn-group { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-top: 1rem; }
        .btn {
            background: #4b5563; color: white; border: none; padding: 0.7rem 1.5rem;
            border-radius: 0.75rem; font-weight: 600; font-size: 0.95rem; cursor: pointer;
            transition: background 0.15s; text-decoration: none; display: inline-block;
        }
        .btn:hover { background: #6b7280; }
        .file-upload { margin-top: 0.5rem; }
        .custom-param-item { display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0.5rem; }
        .custom-param-item input { flex: 1; }
        .remove-param-btn {
            background: #b91c1c; color: white; border: none; padding: 0.4rem 0.8rem;
            border-radius: 0.5rem; cursor: pointer; font-size: 0.8rem; font-weight: 600;
        }
        .add-param-btn {
            background: #059669; color: white; border: none; padding: 0.5rem 1rem;
            border-radius: 0.5rem; cursor: pointer; font-size: 0.8rem; font-weight: 600;
            margin-top: 0.5rem;
        }
        .small-hint { font-size: 0.75rem; color: #6b7280; margin-top: 0.25rem; }
        hr { border-color: #1f2937; margin: 1.5rem 0; }
        .secret-badge {
            display: none; background: #7f1d1d; color: white; padding: 0.75rem 1rem;
            border-radius: 0.5rem; margin-bottom: 1rem; font-weight: bold; text-align: center;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📄 Генератор ТЗ</h1>
        <p class="subtitle">Заполни форму — получишь готовый документ под свой проект</p>

        <!-- Плашка СЕКРЕТНО -->
        <div id="secretBadge" class="secret-badge">🔒 СЕКРЕТНО — проект под NDA</div>

        <form id="briefForm" method="POST" action="/generate-brief" enctype="multipart/form-data">
            <!-- Название -->
            <div class="form-section">
                <label>📌 Название проекта</label>
                <input type="text" name="project_name" placeholder="Введи название" required>
            </div>

            <!-- Тип проекта -->
            <div class="form-section">
                <h2>Что нужно сделать?</h2>
                <div class="radio-group">
                    <label><input type="radio" name="project_type" value="script" onchange="toggleFields(this.value)"> 📜 Скрипт</label>
                    <label><input type="radio" name="project_type" value="website" onchange="toggleFields(this.value)"> 🌐 Сайт</label>
                    <label><input type="radio" name="project_type" value="automation" onchange="toggleFields(this.value)"> ⚙️ Автоматизация</label>
                    <label><input type="radio" name="project_type" value="other" onchange="toggleFields(this.value)" checked> 🤷 Другое</label>
                </div>

                <div id="fields_other" class="conditional active">
                    <label>Опиши проект</label>
                    <textarea name="other_description" rows="3" placeholder="Что хочешь создать, какую задачу решить..."></textarea>
                </div>
                <div id="fields_script" class="conditional">
                    <label>Цель скрипта</label>
                    <textarea name="script_purpose" rows="2" placeholder="Например: парсинг данных..."></textarea>
                    <label style="margin-top:1rem;">Задачи</label>
                    <textarea name="script_tasks" rows="2" placeholder="Конкретные задачи"></textarea>
                    <label style="margin-top:1rem;">Для каких устройств</label>
                    <input type="text" name="script_devices" placeholder="ПК, телефон, планшет, бумага…">
                </div>
                <div id="fields_website" class="conditional">
                    <label>Название сайта</label>
                    <input type="text" name="site_name" placeholder="Мой проект">
                    <label style="margin-top:1rem;">Тематика</label>
                    <input type="text" name="site_theme" placeholder="e-commerce, блог...">
                    <label style="margin-top:1rem;">Цветовая палитра</label>
                    <input type="text" name="site_colors" placeholder="Красный, синий, #4f46e5">
                    <label style="margin-top:1rem;">Описание</label>
                    <textarea name="site_description" rows="3" placeholder="Общее описание сайта..."></textarea>
                </div>
                <div id="fields_automation" class="conditional">
                    <label>Ссылка (на систему)</label>
                    <input type="url" name="auto_url" placeholder="https://...">
                    <label style="margin-top:1rem;">Описание процесса</label>
                    <textarea name="auto_process" rows="2" placeholder="Что автоматизируем, шаги..."></textarea>
                    <label style="margin-top:1rem;">Интеграции / сервисы</label>
                    <textarea name="auto_integrations" rows="2" placeholder="Google Sheets, Telegram..."></textarea>
                </div>
            </div>

            <!-- Уровень детализации -->
            <div class="form-section">
                <h2>Уровень проработки</h2>
                <div class="radio-group">
                    <label><input type="radio" name="detail_level" value="ready" checked> 🎯 Готовое решение</label>
                    <label><input type="radio" name="detail_level" value="detailed"> 📋 Детальный проект</label>
                    <label><input type="radio" name="detail_level" value="template"> 📦 Шаблон</label>
                </div>
                <div class="small-hint">Выберите, насколько подробно описать задачу.</div>
            </div>

            <!-- Аудитория -->
            <div class="form-section">
                <h2>Кто будет использовать?</h2>
                <textarea name="audience" rows="2" placeholder="Целевая аудитория, роли..."></textarea>
            </div>

            <!-- Бюджет -->
            <div class="form-section">
                <h2>💰 Бюджет / Цена</h2>
                <input type="text" name="budget" placeholder="1000 ₽, 50 $, 3 пачки сухариков — что угодно">
                <div class="small-hint">Укажите примерную сумму или эквивалент.</div>
            </div>

            <!-- Файлы -->
            <div class="form-section">
                <h2>📎 Файлы и референсы <span class="optional">(необязательно)</span></h2>
                <input type="file" name="attachments" multiple class="file-upload">
                <div class="small-hint">Можно прикрепить скриншоты, макеты, примеры.</div>
            </div>

            <!-- Уточняющие вопросы -->
            <hr>
            <div class="form-section">
                <h2>📝 Уточняющие вопросы <span class="optional">(необязательно)</span></h2>
                <label>Когда нужно сдать результат?</label>
                <input type="text" name="deadline" placeholder="Например: через 2 недели, к 1 сентября">
                <label style="margin-top:1rem;">Есть ли примеры похожих проектов?</label>
                <textarea name="references" rows="2" placeholder="Ссылки или описание того, что вам нравится"></textarea>
                <label style="margin-top:1rem;">По каким признакам вы поймёте, что всё готово?</label>
                <textarea name="success_criteria" rows="2" placeholder="Что должно работать, какие функции выполняться"></textarea>
                <label style="margin-top:1rem;">Есть ли особые требования по устройствам?</label>
                <textarea name="restrictions" rows="2" placeholder="Например: должно работать на телефоне, только в Windows, и т.д."></textarea>
                <label style="margin-top:1rem;">Сколько примерно человек будет пользоваться?</label>
                <input type="text" name="users_count" placeholder="Например: 10, 1000, миллион">
                <label style="margin-top:1rem;">Нужно ли, чтобы люди входили в систему (логин, пароль)?</label>
                <select name="authorization">
                    <option value="">— Не знаю —</option>
                    <option value="no">Не нужно</option>
                    <option value="yes">Нужно</option>
                </select>
                <label style="margin-top:1rem;">В каком виде ожидаете готовую работу?</label>
                <textarea name="delivery_format" rows="2" placeholder="Ссылка на сайт, файлы, код, документ..."></textarea>
                <label style="margin-top:1rem;">Можно ли обсуждать проект открыто?</label>
                <select name="confidentiality" id="confidentialitySelect" onchange="toggleSecretBadge()">
                    <option value="">— Не важно —</option>
                    <option value="public">Можно</option>
                    <option value="secret">Нельзя (секретно)</option>
                </select>
            </div>

            <!-- Контакты -->
            <hr>
            <div class="form-section">
                <h2>📞 Контакты <span class="optional">(необязательно)</span></h2>
                <label>Как к вам обращаться</label>
                <input type="text" name="contact_name" placeholder="Ваше имя или ник">
                <label style="margin-top:1rem;">Email</label>
                <input type="email" name="contact_email" placeholder="you@example.com">
                <label style="margin-top:1rem;">Телефон</label>
                <input type="tel" name="contact_phone" placeholder="+7 900 123-45-67">
                <label style="margin-top:1rem;">Telegram / Никнейм</label>
                <input type="text" name="contact_telegram" placeholder="@username">
                <label style="margin-top:1rem;">Как лучше связаться?</label>
                <input type="text" name="contact_method" placeholder="Например: Telegram, звонок, письмо">
            </div>

            <!-- Сложные технические настройки -->
            <details class="hidden-panel">
                <summary>Сложные настройки (технологии, архитектура, окружение)</summary>
                <div style="margin-top:1.5rem;">
                    <label>Язык / технологии</label>
                    <select name="tech_stack" id="tech_stack_select" onchange="toggleCustomLang()">
                        <option value="">— Не важно —</option>
                        <option value="Python">Python</option>
                        <option value="Java">Java</option>
                        <option value="C++">C++</option>
                        <option value="C#">C#</option>
                        <option value="JavaScript">JavaScript</option>
                        <option value="other">Другое (указать ниже)</option>
                    </select>
                    <div id="custom_lang_block" style="display: none; margin-top:0.75rem;">
                        <label>🖊️ Свой язык</label>
                        <input type="text" name="custom_language" placeholder="Rust, Go...">
                    </div>
                    <label style="margin-top:1.5rem;">Архитектура проекта</label>
                    <select name="architecture">
                        <option value="">— Не важно —</option>
                        <option value="monolith">Монолит (всё в одном)</option>
                        <option value="microservices">Микросервисы (несколько частей)</option>
                        <option value="serverless">Бессерверная (Serverless)</option>
                    </select>
                    <label style="margin-top:1.5rem;">Базы данных</label>
                    <textarea name="databases" rows="2" placeholder="Какие данные нужно хранить? Нужна ли база данных?"></textarea>
                    <label style="margin-top:1.5rem;">Где будет работать?</label>
                    <textarea name="hosting" rows="2" placeholder="Хостинг, облако, локально на компьютере..."></textarea>
                    <label style="margin-top:1.5rem;">Нужно ли тестирование?</label>
                    <select name="testing">
                        <option value="">— Не важно —</option>
                        <option value="no">Не требуется</option>
                        <option value="auto">Автоматические тесты</option>
                        <option value="manual">Ручная проверка</option>
                    </select>
                    <label style="margin-top:1.5rem;">Документация</label>
                    <select name="documentation">
                        <option value="">— Не важно —</option>
                        <option value="no">Не нужна</option>
                        <option value="brief">Краткая инструкция</option>
                        <option value="full">Подробная документация</option>
                    </select>
                    <label style="margin-top:1.5rem;">Дальнейшая поддержка</label>
                    <select name="support">
                        <option value="">— Не важно —</option>
                        <option value="no">Не нужна</option>
                        <option value="short">Месяц после сдачи</option>
                        <option value="long">Долгосрочная</option>
                    </select>
                    <label style="margin-top:1.5rem;">Доработка / внедрение?</label>
                    <select name="future_plans">
                        <option value="no">Нет</option>
                        <option value="later">Возможна доработка позже</option>
                        <option value="integration">Да, интеграция в другой проект</option>
                    </select>
                    <label style="margin-top:1.5rem;">Дополнительные требования</label>
                    <textarea name="extra_requirements" rows="2" placeholder="Версии, безопасность, производительность..."></textarea>
                </div>
            </details>

            <!-- Свои параметры -->
            <div class="form-section" style="margin-top:1.5rem;">
                <h2>🔧 Свои параметры <span class="optional">(по желанию)</span></h2>
                <div id="customParamsList"></div>
                <button type="button" class="add-param-btn" onclick="addCustomParam()">+ Добавить</button>
                <input type="hidden" name="custom_params_json" id="customParamsJson" value="{}">
            </div>

            <!-- Группа кнопок: основные скачивания -->
            <div class="btn-group">
                <button type="submit" name="format" value="md" class="btn">📥 Скачать MD</button>
                <button type="submit" name="format" value="txt" class="btn">📥 Скачать TXT</button>
                <button type="submit" name="format" value="pdf" class="btn">📥 Скачать PDF</button>
            </div>

            <!-- Группа кнопок: дополнительные действия -->
            <div class="btn-group" style="margin-top: 0.5rem;">
                <button type="button" class="btn" onclick="copyTXT()">📋 Копировать TXT</button>
                <button type="submit" name="format" value="zip" class="btn">🗂️ Скачать ZIP</button>
            </div>
        </form>
    </div>

    <script>
        function toggleFields(t){
            document.querySelectorAll('.conditional').forEach(e=>e.classList.remove('active'));
            const a=document.getElementById('fields_'+t);
            if(a)a.classList.add('active');
        }
        toggleFields('other');

        function toggleCustomLang(){
            const sel = document.getElementById('tech_stack_select');
            const blk = document.getElementById('custom_lang_block');
            blk.style.display = sel.value === 'other' ? 'block' : 'none';
        }

        // Плашка секретности
        function toggleSecretBadge(){
            const select = document.getElementById('confidentialitySelect');
            const badge = document.getElementById('secretBadge');
            if(select.value === 'secret'){
                badge.style.display = 'block';
            } else {
                badge.style.display = 'none';
            }
        }
        // Проверка при загрузке
        window.addEventListener('load', toggleSecretBadge);

        function updateJson(){let d={};document.querySelectorAll('.custom-param-item').forEach(i=>{const k=i.querySelector('.param-key').value.trim(),v=i.querySelector('.param-value').value;if(k)d[k]=v});document.getElementById('customParamsJson').value=JSON.stringify(d)}
        function removeParam(b){b.parentElement.remove();updateJson()}
        function addCustomParam(){const c=document.getElementById('customParamsList'),d=document.createElement('div');d.className='custom-param-item';d.innerHTML='<input type="text" class="param-key" placeholder="Название" oninput="updateJson()"><input type="text" class="param-value" placeholder="Значение" oninput="updateJson()"><button type="button" class="remove-param-btn" onclick="removeParam(this)">✕</button>';c.appendChild(d);updateJson()}

        async function copyTXT(){
            const form = document.getElementById('briefForm');
            const fd = new FormData(form);
            fd.append('format','txt');
            try{
                const res = await fetch('/generate-brief', {method:'POST', body:fd});
                const txt = await res.text();
                await navigator.clipboard.writeText(txt);
                alert('Текст скопирован!');
            }catch(e){alert('Не удалось скопировать. Разрешите буфер обмена или попробуйте через HTTPS.');}
        }
    </script>
</body>
</html>
'''

# -------- Шрифт --------
FONT_PATH = None

def get_font_path():
    global FONT_PATH
    if FONT_PATH and os.path.exists(FONT_PATH):
        return FONT_PATH
    if sys.platform == 'win32':
        arial = r'C:\Windows\Fonts\arial.ttf'
        if os.path.exists(arial):
            FONT_PATH = arial
            return FONT_PATH
    script_dir = os.path.dirname(__file__)
    for f in os.listdir(script_dir):
        if f.lower().endswith('.ttf'):
            FONT_PATH = os.path.join(script_dir, f)
            return FONT_PATH
    raise FileNotFoundError("Не найден шрифт с кириллицей. Положите Arial.ttf в папку со скриптом.")

# -------- Цвета --------
def parse_color(text):
    if not text: return None
    match = re.search(r'#[0-9a-fA-F]{6}', text)
    if match:
        try: return HexColor(match.group(0))
        except: pass
    named = {'красный':'#FF0000','синий':'#0000FF','зелёный':'#008000',
             'чёрный':'#000000','белый':'#FFFFFF','жёлтый':'#FFFF00',
             'оранжевый':'#FFA500','фиолетовый':'#800080'}
    for name, h in named.items():
        if name in text.lower(): return HexColor(h)
    return None

# -------- PDF --------
def draw_formatted_text(c, text, x, y, font_name, font_size, color=None, max_width=None):
    if not max_width: max_width = A4[0] - 2*x
    bold_font = font_name + '-Bold'
    parts = re.split(r'(\*\*.*?\*\*)', text)
    cur_x = x
    for part in parts:
        if part.startswith('**') and part.endswith('**'):
            c.setFont(bold_font, font_size)
            txt = part[2:-2]
        else:
            c.setFont(font_name, font_size)
            txt = part
        if color: c.setFillColor(color)
        else: c.setFillColor(Color(0,0,0))
        c.drawString(cur_x, y, txt)
        cur_x += c.stringWidth(txt, c._fontname, font_size)

def generate_pdf(md_text, accent_color=None):
    font_path = get_font_path()
    if 'CustomFont' not in pdfmetrics._fonts:
        pdfmetrics.registerFont(TTFont('CustomFont', font_path))
    bold_path = font_path.replace('.ttf', '-Bold.ttf')
    if os.path.exists(bold_path):
        pdfmetrics.registerFont(TTFont('CustomFont-Bold', bold_path))
    else:
        pdfmetrics.registerFont(TTFont('CustomFont-Bold', font_path))

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    x_left = 25*mm
    x_bullet = 30*mm
    y = A4[1] - 20*mm
    line_height = 6*mm

    for line in md_text.split('\n'):
        stripped = line.strip()
        if not stripped:
            y -= line_height * 0.5
            continue
        if stripped.startswith('# ') and not stripped.startswith('## '):
            title = stripped[2:]
            c.setFont('CustomFont-Bold', 16)
            c.setFillColor(accent_color if accent_color else Color(0,0,0))
            c.drawString(x_left, y, title)
            y -= line_height * 1.5
        elif stripped.startswith('## '):
            title = stripped[3:]
            c.setFont('CustomFont-Bold', 14)
            c.setFillColor(accent_color if accent_color else Color(0,0,0))
            c.drawString(x_left, y, title)
            y -= line_height * 1.3
        elif stripped.startswith('- '):
            item = stripped[2:]
            c.setFont('CustomFont', 11)
            c.setFillColor(Color(0,0,0))
            c.circle(x_left + 1.5*mm, y + 1.5*mm, 0.8*mm, fill=1)
            draw_formatted_text(c, item, x_bullet, y, 'CustomFont', 11, None, A4[0]-2*x_bullet)
            y -= line_height
        else:
            c.setFont('CustomFont', 11)
            c.setFillColor(Color(0,0,0))
            draw_formatted_text(c, stripped, x_left, y, 'CustomFont', 11, None, A4[0]-2*x_left)
            y -= line_height
        if y < 25*mm:
            c.showPage()
            y = A4[1] - 20*mm
    c.save()
    buf.seek(0)
    return buf

def strip_markdown(text):
    text = re.sub(r'^#+ ', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'^- ', '', text, flags=re.MULTILINE)
    return text

# -------- Маршруты --------
@app.route('/')
def index():
    return redirect('/generate-brief')

@app.route('/generate-brief', methods=['GET', 'POST'])
def generate_brief():
    if request.method == 'POST':
        data = request.form
        files = request.files.getlist('attachments')
        saved_files = []
        for f in files:
            if f.filename:
                fname = f.filename
                fpath = os.path.join(UPLOAD_DIR, fname)
                f.save(fpath)
                saved_files.append((fname, fpath))

        project_name = data.get('project_name', 'Без названия')
        project_type = data.get('project_type', 'other')
        detail_level = data.get('detail_level', 'ready')
        audience = data.get('audience', '')
        budget = data.get('budget', '')

        tech_stack = data.get('tech_stack', '')
        custom_language = data.get('custom_language', '').strip()
        architecture = data.get('architecture', '')
        databases = data.get('databases', '')
        hosting = data.get('hosting', '')
        testing = data.get('testing', '')
        documentation = data.get('documentation', '')
        support = data.get('support', '')
        future_plans = data.get('future_plans', 'no')
        extra = data.get('extra_requirements', '')
        site_colors = data.get('site_colors', '')

        deadline = data.get('deadline', '')
        references = data.get('references', '')
        success_criteria = data.get('success_criteria', '')
        restrictions = data.get('restrictions', '')
        users_count = data.get('users_count', '')
        authorization = data.get('authorization', '')
        delivery_format = data.get('delivery_format', '')
        confidentiality = data.get('confidentiality', '')

        contact_name = data.get('contact_name', '')
        contact_email = data.get('contact_email', '')
        contact_phone = data.get('contact_phone', '')
        contact_telegram = data.get('contact_telegram', '')
        contact_method = data.get('contact_method', '')

        final_lang = custom_language if custom_language else (tech_stack if tech_stack != 'other' else '')
        accent_color = None
        if project_type == 'website' and site_colors:
            accent_color = parse_color(site_colors)

        other_desc = data.get('other_description', '')
        script_purpose = data.get('script_purpose', '')
        script_tasks = data.get('script_tasks', '')
        script_devices = data.get('script_devices', '')
        site_name = data.get('site_name', '')
        site_theme = data.get('site_theme', '')
        site_description = data.get('site_description', '')
        auto_url = data.get('auto_url', '')
        auto_process = data.get('auto_process', '')
        auto_integrations = data.get('auto_integrations', '')

        custom_json = data.get('custom_params_json', '{}')
        try: custom_params = json.loads(custom_json)
        except: custom_params = {}

        md = f"# {project_name}\n\n"
        if confidentiality == 'secret':
            md += "**🔒 СЕКРЕТНО — проект под NDA**\n\n"
        md += f"**Тип:** {project_type}  \n"
        md += f"**Уровень проработки:** {detail_level}\n\n"

        if project_type == 'other':
            md += "## Описание\n" + (other_desc or '-') + "\n"
        elif project_type == 'script':
            md += "## Скрипт\n"
            md += f"- Цель: {script_purpose or '-'}\n- Задачи: {script_tasks or '-'}\n- Устройства: {script_devices or '-'}\n"
        elif project_type == 'website':
            md += "## Сайт\n"
            md += f"- Название: {site_name or '-'}\n- Тематика: {site_theme or '-'}\n- Палитра: {site_colors or '-'}\n- Описание: {site_description or '-'}\n"
        elif project_type == 'automation':
            md += "## Автоматизация\n"
            md += f"- Ссылка: {auto_url or '-'}\n- Процесс: {auto_process or '-'}\n- Интеграции: {auto_integrations or '-'}\n"

        md += "\n## Аудитория\n" + (audience or '-') + "\n"
        if budget: md += f"\n## Бюджет\n{budget}\n"

        tech_used = []
        if final_lang: tech_used.append(f"- Язык: {final_lang}")
        if architecture: tech_used.append(f"- Архитектура: {architecture}")
        if databases: tech_used.append(f"- Базы данных: {databases}")
        if hosting: tech_used.append(f"- Хостинг/окружение: {hosting}")
        if testing: tech_used.append(f"- Тестирование: {testing}")
        if documentation: tech_used.append(f"- Документация: {documentation}")
        if support: tech_used.append(f"- Поддержка: {support}")
        if future_plans != 'no':
            plan_map = {'later': 'Возможна доработка позже', 'integration': 'Да, интеграция в другой проект'}
            tech_used.append(f"- Планы: {plan_map.get(future_plans, future_plans)}")
        if extra: tech_used.append(f"- Доп. требования: {extra}")
        if tech_used:
            md += "\n## Технические детали\n" + "\n".join(tech_used) + "\n"

        if deadline: md += f"\n## Сроки\n{deadline}\n"
        if references: md += f"\n## Примеры\n{references}\n"
        if success_criteria: md += f"\n## Ожидаемый результат\n{success_criteria}\n"
        if restrictions: md += f"\n## Ограничения\n{restrictions}\n"
        if users_count: md += f"\n## Количество пользователей\n{users_count}\n"
        if authorization: md += f"\n## Авторизация\n{'Нужна' if authorization=='yes' else 'Не нужна'}\n"
        if delivery_format: md += f"\n## Формат сдачи\n{delivery_format}\n"
        if confidentiality:
            conf_text = 'Можно' if confidentiality == 'public' else 'Нельзя (секретно)'
            md += f"\n## Конфиденциальность\n{conf_text}\n"

        if custom_params:
            md += "\n## Дополнительные параметры\n"
            for k, v in custom_params.items(): md += f"- **{k}**: {v}\n"

        if saved_files:
            md += "\n## Прикреплённые файлы\n"
            for fname, _ in saved_files: md += f"- {fname}\n"

        contacts = []
        if contact_name: contacts.append(f"- Обращаться: {contact_name}")
        if contact_email: contacts.append(f"- Email: {contact_email}")
        if contact_phone: contacts.append(f"- Телефон: {contact_phone}")
        if contact_telegram: contacts.append(f"- Telegram: {contact_telegram}")
        if contact_method: contacts.append(f"- Способ связи: {contact_method}")
        if contacts:
            md += "\n## Контакты\n" + "\n".join(contacts) + "\n"

        fmt = data.get('format', 'md')
        if fmt == 'zip':
            zip_buf = BytesIO()
            with zipfile.ZipFile(zip_buf, 'w') as zf:
                zf.writestr(f'{project_name}_tech_spec.md', md)
                zf.writestr(f'{project_name}_tech_spec.txt', strip_markdown(md))
                pdf_buf = generate_pdf(md, accent_color)
                zf.writestr(f'{project_name}_tech_spec.pdf', pdf_buf.getvalue())
                for fname, fpath in saved_files:
                    zf.write(fpath, arcname=fname)
            zip_buf.seek(0)
            buf = zip_buf
            fname = f'{project_name}_tech_spec.zip'
            mime = 'application/zip'
        elif fmt == 'md':
            buf = BytesIO(md.encode('utf-8'))
            fname = f"{project_name}_tech_spec.md"
            mime = 'text/markdown'
        elif fmt == 'txt':
            plain = strip_markdown(md)
            buf = BytesIO(plain.encode('utf-8'))
            fname = f"{project_name}_tech_spec.txt"
            mime = 'text/plain'
        elif fmt == 'pdf':
            buf = generate_pdf(md, accent_color)
            fname = f"{project_name}_tech_spec.pdf"
            mime = 'application/pdf'
        else:
            return "Неизвестный формат", 400

        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=fname, mimetype=mime)

    return render_template_string(HTML_TEMPLATE)

if __name__ == '__main__':
    app.run(debug=True)
