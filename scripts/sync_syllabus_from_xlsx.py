#!/usr/bin/env python3
"""Sync syllabus content from syllabus.xlsx into assets/js/main.js."""

import argparse
import os
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

NS = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def parse_shared_strings(zf):
    if 'xl/sharedStrings.xml' not in zf.namelist():
        return []
    root = ET.fromstring(zf.read('xl/sharedStrings.xml'))
    strings = []
    for si in root.findall('main:si', NS):
        text = ''.join(t.text or '' for t in si.findall('.//main:t', NS))
        strings.append(text)
    return strings


def parse_sheet(zf, shared_strings, sheet_name='xl/worksheets/sheet1.xml'):
    if sheet_name not in zf.namelist():
        raise FileNotFoundError(f'Missing worksheet: {sheet_name}')
    root = ET.fromstring(zf.read(sheet_name))
    rows = []
    for row in root.findall('.//main:row', NS):
        row_values = {}
        for cell in row.findall('main:c', NS):
            address = cell.get('r', '')
            col = ''.join([c for c in address if c.isalpha()])
            value_element = cell.find('main:v', NS)
            if value_element is None:
                continue
            raw_value = value_element.text or ''
            cell_type = cell.get('t')
            if cell_type == 's':
                value = shared_strings[int(raw_value)]
            elif cell_type == 'b':
                value = 'TRUE' if raw_value == '1' else 'FALSE'
            else:
                value = raw_value
            row_values[col] = value
        rows.append(row_values)
    return rows


def dx_column_name(col):
    return re.sub(r'[^0-9A-Za-z]', '', col).lower()


def normalize_value(value):
    if value is None:
        return ''
    stripped = str(value).strip()
    return stripped


def parse_boolean(value):
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in ('1', 'true', 'yes', 'y')


def format_js_string(text):
    escaped = str(text).replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'


def build_week_object(row, header_map):
    if not header_map.get('week') or header_map['week'] not in row:
        return None
    week_text = row.get(header_map['week'], '').strip()
    if not week_text:
        return None
    try:
        week_number = int(float(week_text))
    except ValueError:
        week_number = week_text
    title = normalize_value(row.get(header_map.get('title', ''), ''))
    chapter = normalize_value(row.get(header_map.get('chapter', ''), ''))
    topics = []
    for key in ['topic1', 'topic2', 'topic3']:
        col = header_map.get(key)
        if col:
            topic = normalize_value(row.get(col, ''))
            if topic:
                topics.append(topic)
    week_obj = {'w': week_number, 'title': title, 'ch': chapter, 'topics': topics}
    if 'currentweek' in header_map:
        value = normalize_value(row.get(header_map['currentweek'], ''))
        if parse_boolean(value):
            week_obj['current'] = True
    if 'haslecture' in header_map:
        value = normalize_value(row.get(header_map['haslecture'], ''))
        if parse_boolean(value):
            week_obj['hasLecture'] = True
    return week_obj


def build_js_block(weeks):
    lines = ['// SYLLABUS_START', 'const weeks = [']
    for week in weeks:
        props = [f'w:{week["w"]}', f'title:{format_js_string(week["title"])}', f'ch:{format_js_string(week["ch"])}']
        topics = ','.join(format_js_string(t) for t in week['topics'])
        props.append(f'topics:[{topics}]')
        if week.get('current'):
            props.append('current:true')
        if week.get('hasLecture'):
            props.append('hasLecture:true')
        lines.append('  {' + ','.join(props) + '},')
    if len(lines) > 2:
        lines[-1] = lines[-1].rstrip(',')
    lines.append('];')
    lines.append('// SYLLABUS_END')
    return '\n'.join(lines) + '\n'


def replace_js_syllabus(js_path, new_block):
    with open(js_path, 'r', encoding='utf-8') as f:
        content = f.read()
    if '// SYLLABUS_START' in content and '// SYLLABUS_END' in content:
        pattern = re.compile(r'// SYLLABUS_START\n.*?// SYLLABUS_END\n', re.S)
    else:
        pattern = re.compile(r'const weeks = \[\n.*?\];\n', re.S)
    updated, count = pattern.subn(new_block, content, count=1)
    if count == 0:
        raise RuntimeError('Unable to locate the syllabus block in main.js')
    with open(js_path, 'w', encoding='utf-8') as f:
        f.write(updated)
    return count


def main():
    parser = argparse.ArgumentParser(description='Sync syllabus.xlsx into assets/js/main.js')
    parser.add_argument('--xlsx', default='syllabus.xlsx', help='Path to the XLSX file')
    parser.add_argument('--js', default='assets/js/main.js', help='Path to main.js')
    args = parser.parse_args()

    xlsx_path = os.path.abspath(args.xlsx)
    js_path = os.path.abspath(args.js)

    if not os.path.exists(xlsx_path):
        print(f'Error: XLSX file not found: {xlsx_path}', file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(js_path):
        print(f'Error: JS file not found: {js_path}', file=sys.stderr)
        sys.exit(1)

    with zipfile.ZipFile(xlsx_path, 'r') as zf:
        shared_strings = parse_shared_strings(zf)
        rows = parse_sheet(zf, shared_strings)

    if not rows:
        print('Error: No rows found in the worksheet', file=sys.stderr)
        sys.exit(1)

    header_row = rows[0]
    header_map = {}
    for col, value in header_row.items():
        normalized = dx_column_name(value)
        if normalized in ('week', 'title', 'chapter', 'topic1', 'topic2', 'topic3', 'currentweek', 'haslecture'):
            header_map[normalized] = col

    if 'week' not in header_map or 'title' not in header_map or 'chapter' not in header_map:
        print('Error: XLSX sheet must include Week, Title, and Chapter columns', file=sys.stderr)
        sys.exit(1)

    syllabus = []
    for row in rows[1:]:
        week_obj = build_week_object(row, header_map)
        if week_obj is not None:
            syllabus.append(week_obj)

    if not syllabus:
        print('Error: No syllabus rows were parsed', file=sys.stderr)
        sys.exit(1)

    new_block = build_js_block(syllabus)
    count = replace_js_syllabus(js_path, new_block)
    print(f'Successfully updated {count} syllabus block(s) in {js_path}')


if __name__ == '__main__':
    main()
