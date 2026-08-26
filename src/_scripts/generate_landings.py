#!/usr/bin/env python3
"""Generate AIP v1.1 case landing pages and SVG assets from content registry."""

import json
import math
import os
import shutil
import textwrap
from pathlib import Path

import jinja2

ROOT = Path(__file__).resolve().parents[1]  # cases/ai-portfolio/src
DATA_FILE = ROOT / "_data" / "aip-v11-landings.json"
CASES_DIR = ROOT / "cases"
ASSETS_DIR = ROOT / "assets" / "cases"
SCREENSHOTS_DIR = ROOT / "assets" / "screenshots"

# Site-root relative asset prefix used in HTML src/href.
ASSET_PREFIX = "/assets/cases"
SCREENSHOT_PREFIX = "/assets/screenshots"

# Cases whose HTML is maintained manually and must not be overwritten by the generator.
MANUAL_CASES = {"ai-curator"}


def ensure_dirs():
    (ROOT / "_data").mkdir(parents=True, exist_ok=True)
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def rel_to_root(path: str) -> Path:
    """Resolve a path written relative to ai-portfolio/src root (e.g. ../ai-data-assistant/...)."""
    if path.startswith("/"):
        return Path(path)
    return (ROOT / path).resolve()


def copy_to_assets(src: Path, dest_dir: Path, dest_name: str) -> str:
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(src).suffix
    dest = dest_dir / f"{dest_name}{ext}"
    shutil.copyfile(src, dest)
    return f"{ASSET_PREFIX}/{dest_dir.name}/{dest_name}{ext}"


# ---------------------------------------------------------------------------
# SVG builders
# ---------------------------------------------------------------------------

def pipeline_svg(nodes, aria_label, title_line="") -> str:
    """Build a horizontal or two-row pipeline SVG. Auto-wraps to two rows when > 5 nodes."""
    n = len(nodes)
    if n <= 5:
        return _pipeline_single_row_svg(nodes, aria_label)
    return _pipeline_two_row_svg(nodes, aria_label)


def _pipeline_single_row_svg(nodes, aria_label) -> str:
    """Single-row compact pipeline for <= 5 nodes."""
    n = len(nodes)
    margin_x, margin_y = 24, 30
    node_w, node_h = 170, 80
    gap = 60
    width = margin_x * 2 + node_w * n + gap * (n - 1)
    height = 180
    marker_id = f"arrow-sr-{abs(hash(aria_label)) % 100000}"
    svg = [
        f'<svg class="pipeline-diagram pipeline-diagram--single" viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" aria-label="{escape_attr(aria_label)}">',
        "  <defs>",
        f'    <marker id="{marker_id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">',
        '      <path d="M 0 0 L 10 5 L 0 10 z" class="arrow-head" />',
        '    </marker>',
        '  </defs>',
    ]
    y = (height - node_h) // 2
    for i, node in enumerate(nodes):
        x = margin_x + i * (node_w + gap)
        rect_cls = "node-accent" if node.get("accent") else "node-rect"
        svg.append(f'  <g transform="translate({x}, {y})">')
        svg.append(f'    <rect x="0" y="0" width="{node_w}" height="{node_h}" rx="4" class="{rect_cls}" />')
        title = node.get("title", "")
        lines = node.get("lines", [])
        ty = 24
        svg.append(f'    <text x="{node_w/2}" y="{ty}" text-anchor="middle" class="title-text">{escape_text(title)}</text>')
        for j, line in enumerate(lines[:2]):
            svg.append(f'    <text x="{node_w/2}" y="{ty + 20 + j*16}" text-anchor="middle" class="body-text">{escape_text(line)}</text>')
        svg.append('  </g>')
        if i < n - 1:
            x1 = x + node_w
            x2 = x + node_w + gap
            cy = y + node_h / 2
            svg.append(f'  <path d="M {x1} {cy} L {x2} {cy}" class="arrow" marker-end="url(#{marker_id})" />')
    svg.append('</svg>')
    return "\n".join(svg)


def _pipeline_two_row_svg(nodes, aria_label) -> str:
    """Two-row pipeline for > 5 nodes: larger nodes and text like AIC."""
    n = len(nodes)
    mid = (n + 1) // 2
    top_nodes = nodes[:mid]
    bottom_nodes = nodes[mid:]
    margin_x, margin_y = 40, 28
    node_w, node_h = 210, 94
    gap = 56
    row_gap = 70
    max_in_row = max(len(top_nodes), len(bottom_nodes))
    row_width = margin_x * 2 + node_w * max_in_row + gap * (max_in_row - 1)
    height = margin_y * 2 + node_h * 2 + row_gap
    marker_id = f"arrow-tr-{abs(hash(aria_label)) % 100000}"
    svg = [
        f'<svg class="pipeline-diagram pipeline-diagram--two-row" viewBox="0 0 {row_width} {height}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" aria-label="{escape_attr(aria_label)}">',
        "  <defs>",
        f'    <marker id="{marker_id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">',
        '      <path d="M 0 0 L 10 5 L 0 10 z" class="arrow-head" />',
        '    </marker>',
        '  </defs>',
    ]

    def row_offset(count):
        return (row_width - (margin_x * 2 + node_w * count + gap * (count - 1))) // 2

    # Top row
    top_x = margin_x + row_offset(len(top_nodes))
    top_y = margin_y
    for i, node in enumerate(top_nodes):
        x = top_x + i * (node_w + gap)
        rect_cls = "node-accent" if node.get("accent") else "node-rect"
        svg.append(f'  <g transform="translate({x}, {top_y})">')
        svg.append(f'    <rect x="0" y="0" width="{node_w}" height="{node_h}" rx="5" class="{rect_cls}" />')
        title = node.get("title", "")
        lines = node.get("lines", [])
        ty = 28
        svg.append(f'    <text x="{node_w/2}" y="{ty}" text-anchor="middle" class="title-text title-text--large">{escape_text(title)}</text>')
        for j, line in enumerate(lines[:2]):
            svg.append(f'    <text x="{node_w/2}" y="{ty + 24 + j*18}" text-anchor="middle" class="body-text body-text--large">{escape_text(line)}</text>')
        svg.append('  </g>')
        if i < len(top_nodes) - 1:
            x1 = x + node_w
            x2 = x + node_w + gap
            cy = top_y + node_h / 2
            svg.append(f'  <path d="M {x1} {cy} L {x2} {cy}" class="arrow" marker-end="url(#{marker_id})" />')

    # Connector from last top node to first bottom node:
    # 1) drop halfway between rows, 2) horizontal to middle of first bottom node,
    # 3) vertical arrow down into top edge center of first bottom node.
    last_top_x = top_x + (len(top_nodes) - 1) * (node_w + gap)
    first_bottom_x = margin_x + row_offset(len(bottom_nodes))
    bottom_y = top_y + node_h + row_gap
    drop_x = last_top_x + node_w / 2
    drop_y_top = top_y + node_h
    mid_y = drop_y_top + row_gap / 2
    target_x = first_bottom_x + node_w / 2
    svg.append(f'  <path d="M {drop_x} {drop_y_top} L {drop_x} {mid_y}" class="arrow" />')
    svg.append(f'  <path d="M {drop_x} {mid_y} L {target_x} {mid_y}" class="arrow" />')
    svg.append(f'  <path d="M {target_x} {mid_y} L {target_x} {bottom_y}" class="arrow" marker-end="url(#{marker_id})" />')

    # Bottom row (drawn right-to-left visually if we want flow back? No: keep left-to-right)
    for i, node in enumerate(bottom_nodes):
        x = first_bottom_x + i * (node_w + gap)
        rect_cls = "node-accent" if node.get("accent") else "node-rect"
        svg.append(f'  <g transform="translate({x}, {bottom_y})">')
        svg.append(f'    <rect x="0" y="0" width="{node_w}" height="{node_h}" rx="5" class="{rect_cls}" />')
        title = node.get("title", "")
        lines = node.get("lines", [])
        ty = 28
        svg.append(f'    <text x="{node_w/2}" y="{ty}" text-anchor="middle" class="title-text title-text--large">{escape_text(title)}</text>')
        for j, line in enumerate(lines[:2]):
            svg.append(f'    <text x="{node_w/2}" y="{ty + 24 + j*18}" text-anchor="middle" class="body-text body-text--large">{escape_text(line)}</text>')
        svg.append('  </g>')
        if i < len(bottom_nodes) - 1:
            x1 = x + node_w
            x2 = x + node_w + gap
            cy = bottom_y + node_h / 2
            svg.append(f'  <path d="M {x1} {cy} L {x2} {cy}" class="arrow" marker-end="url(#{marker_id})" />')
    svg.append('</svg>')
    return "\n".join(svg)


def telegram_chat_svg(title, messages, aria_label, width=980, height=540) -> str:
    """Generic Telegram-style chat SVG for scenario illustrations."""
    svg = [
        f'<svg class="ui-illustration" viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" aria-label="{escape_attr(aria_label)}">',
        '  <defs>',
        '    <clipPath id="tg-window-clip">',
        f'      <rect x="20" y="10" width="{width-40}" height="{height-20}" rx="8" />',
        '    </clipPath>',
        '  </defs>',
        f'  <rect x="20" y="10" width="{width-40}" height="{height-20}" rx="8" class="ui-window" />',
        f'  <rect x="20" y="10" width="{width-40}" height="62" class="ui-header" clip-path="url(#tg-window-clip)" />',
        '  <circle cx="48" cy="41" r="12" class="ui-avatar" />',
        f'  <text x="72" y="38" class="ui-title">{escape_text(title)}</text>',
        '  <circle cx="180" cy="41" r="4" fill="#22c55e" />',
        '  <text x="192" y="45" class="ui-subtitle" style="font-size:12px;">Бот онлайн</text>',
    ]
    y = 100
    for msg in messages:
        is_user = msg.get("user", False)
        text = msg.get("text", "")
        h = max(46, 20 + 20 * (len(text) // 55 + 1))
        if is_user:
            x = width - 40 - 420
            cls = "ui-msg-user"
            tcls = "ui-msg-text-user"
            fill = "#ffffff"
        else:
            x = 40
            cls = "ui-msg-bot"
            tcls = "ui-msg-text-bot"
            fill = "var(--text-primary)"
        svg.append(f'  <rect x="{x}" y="{y}" width="420" height="{h}" rx="8" class="{cls}" />')
        # Wrap text roughly
        lines = textwrap.wrap(text, width=55)
        for j, line in enumerate(lines[:3]):
            anchor = "end" if is_user else "start"
            tx = x + 400 if is_user else x + 16
            svg.append(f'  <text x="{tx}" y="{y + 24 + j*18}" text-anchor="{anchor}" class="{tcls}" style="font-size:14px;fill:{fill};">{escape_text(line)}</text>')
        y += h + 16
    svg.append('</svg>')
    return "\n".join(svg)


def hr_scenario_1_svg() -> str:
    """Candidate sends CV in Telegram."""
    return telegram_chat_svg(
        "HR Assistant",
        [
            {"text": "Здравствуйте! Отправьте резюме или ссылку на вакансию.", "user": False},
            {"text": "Отправляю резюме: Иванов Иван, ML Engineer", "user": True},
            {"text": "Резюме получено. Анализируем опыт и соответствие открытым позициям...", "user": False},
            {"text": "Match score: 92/100 · Рекомендуем пригласить на собеседование", "user": False},
        ],
        "HR Assistant: кандидат отправляет резюме в Telegram и получает match score",
    )


def ada_scenario_1_svg() -> str:
    """Scenario 1: AI Data Chat — pie chart fills the full illustration area."""
    w, h = 980, 540
    # Layout: chat area on the LEFT (as in real UI), context sidebar on the RIGHT.
    margin, hdr = 14, 56
    sidebar_w = 230
    chat_x = margin
    chat_w = w - margin * 2 - sidebar_w - 12
    sidebar_x = chat_x + chat_w + 12
    inner_h = h - margin * 2 - hdr
    # Pie sector angles matching 40.6% / 30.7% / 28.7%
    def polar(r, deg):
        rad = math.radians(deg - 90)
        return r * math.cos(rad), r * math.sin(rad)
    angles = [0, 146.16, 256.68, 360]  # cumulative
    svg = [
        f'<svg class="ui-illustration" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" aria-label="AI Data Chat: чат с круговой диаграммой долей revenue по категориям">',
        '  <defs>',
        '    <clipPath id="ada-chat-clip">',
        f'      <rect x="{margin}" y="{margin}" width="{w - margin * 2}" height="{h - margin * 2}" rx="6" />',
        '    </clipPath>',
        '  </defs>',
        # Window + header
        f'  <rect x="{margin}" y="{margin}" width="{w - margin * 2}" height="{h - margin * 2}" rx="6" class="ui-window" />',
        f'  <rect x="{margin}" y="{margin}" width="{w - margin * 2}" height="{hdr}" class="ui-header" clip-path="url(#ada-chat-clip)" />',
        f'  <circle cx="42" cy="{margin + hdr // 2}" r="14" class="ui-avatar" />',
        f'  <text x="66" y="{margin + 30}" class="ui-title">AI Data Chat</text>',
        f'  <text x="66" y="{margin + 48}" class="ui-subtitle" style="font-size:12px;">чат для файлов, графиков и отчётов</text>',
        f'  <rect x="{w - margin - 150}" y="{margin + 14}" width="135" height="30" rx="4" class="ui-toggle" />',
        f'  <text x="{w - margin - 82}" y="{margin + 34}" text-anchor="middle" class="ui-sidebar-text" style="font-size:12px;">Новый чат</text>',
        # Chat area (LEFT)
        f'  <rect x="{chat_x}" y="{margin + hdr}" width="{chat_w}" height="{inner_h}" fill="var(--bg)" clip-path="url(#ada-chat-clip)" />',
        # User request
        f'  <rect x="{chat_x + chat_w - 360}" y="{margin + hdr + 16}" width="360" height="40" rx="6" class="ui-msg-user" />',
        f'  <text x="{chat_x + chat_w - 180}" y="{margin + hdr + 41}" text-anchor="middle" class="ui-msg-text-user" style="font-size:13px;">Построй круговую по категориям</text>',
        # Bot response bubble (large, fills chat area)
        f'  <rect x="{chat_x + 12}" y="{margin + hdr + 70}" width="{chat_w - 24}" height="{inner_h - 130}" rx="8" class="ui-msg-bot" />',
        f'  <text x="{chat_x + 32}" y="{margin + hdr + 100}" class="ui-msg-text-bot" style="font-size:15px; font-weight:600;">Доли «revenue» по категориям «category»</text>',
        f'  <text x="{chat_x + 32}" y="{margin + hdr + 124}" class="ui-msg-text-bot-muted" style="font-size:12px;">Pie chart: category</text>',
        # Pie chart centered in bot bubble, ~full height
        f'  <g transform="translate({chat_x + chat_w // 2 - 10}, {margin + hdr + 70 + (inner_h - 130) // 2})">',
    ]
    R = min(chat_w - 130, inner_h - 210) // 2
    colors = ['var(--accent)', 'var(--accent-soft)', 'var(--text-muted)']
    labels = [('Services', '40.6%', 163), ('Software', '30.7%', 232), ('Hardware', '28.7%', 300)]
    for i in range(3):
        a1, a2 = angles[i], angles[i + 1]
        x1, y1 = polar(R, a1)
        x2, y2 = polar(R, a2)
        large = 1 if (a2 - a1) > 180 else 0
        svg.append(f'    <path d="M0 0 L{x1:.1f} {y1:.1f} A{R} {R} 0 {large} 1 {x2:.1f} {y2:.1f} Z" fill="{colors[i]}" />')
    svg.append('  </g>')
    # Labels on the right side of pie
    for name, pct, y_off in labels:
        svg.append(f'  <rect x="{chat_x + chat_w - 138}" y="{margin + hdr + y_off}" width="110" height="18" rx="3" class="ui-source-card" />')
        svg.append(f'  <text x="{chat_x + chat_w - 83}" y="{margin + hdr + y_off + 13}" text-anchor="middle" class="ui-sidebar-text" style="font-size:11px;">{name} {pct}</text>')
    # Input bar
    svg.extend([
        f'  <rect x="{chat_x + 12}" y="{margin + hdr + inner_h - 46}" width="{chat_w - 24}" height="36" rx="18" class="ui-input" />',
        f'  <text x="{chat_x + 38}" y="{margin + hdr + inner_h - 24}" class="ui-input-text" style="font-size:12px;">Например: проанализируй файл, построй histogram...</text>',
        f'  <circle cx="{chat_x + chat_w - 34}" cy="{margin + hdr + inner_h - 28}" r="12" class="ui-send" />',
        f'  <path d="M{chat_x + chat_w - 42} {margin + hdr + inner_h - 28} L{chat_x + chat_w - 26} {margin + hdr + inner_h - 28} M{chat_x + chat_w - 30} {margin + hdr + inner_h - 34} L{chat_x + chat_w - 26} {margin + hdr + inner_h - 28} L{chat_x + chat_w - 30} {margin + hdr + inner_h - 22}" class="ui-send-arrow" />',
        # Sidebar (RIGHT)
        f'  <rect x="{sidebar_x}" y="{margin + hdr}" width="{sidebar_w}" height="{inner_h}" class="ui-sidebar" clip-path="url(#ada-chat-clip)" />',
        f'  <text x="{sidebar_x + 16}" y="{margin + hdr + 28}" class="ui-sidebar-title">Текущий контекст</text>',
        f'  <rect x="{sidebar_x + 16}" y="{margin + hdr + 42}" width="{sidebar_w - 32}" height="70" rx="6" class="ui-source-card" />',
        f'  <text x="{sidebar_x + 30}" y="{margin + hdr + 70}" class="ui-source-title" style="font-size:13px;">sample_sales.csv</text>',
        f'  <text x="{sidebar_x + 30}" y="{margin + hdr + 90}" class="ui-subtitle" style="font-size:11px;">8 строк · 6 колонок · 3 numeric</text>',
        f'  <rect x="{sidebar_x + 16}" y="{margin + hdr + 124}" width="{sidebar_w - 32}" height="34" rx="4" class="ui-btn-primary" />',
        f'  <text x="{sidebar_x + sidebar_w // 2}" y="{margin + hdr + 146}" text-anchor="middle" class="ui-btn-text" style="font-size:12px;">Сделать анализ</text>',
        f'  <rect x="{sidebar_x + 16}" y="{margin + hdr + 168}" width="{sidebar_w - 32}" height="34" rx="4" class="ui-toggle" />',
        f'  <text x="{sidebar_x + sidebar_w // 2}" y="{margin + hdr + 190}" text-anchor="middle" class="ui-sidebar-text" style="font-size:12px;">Построить график</text>',
        f'  <rect x="{sidebar_x + 16}" y="{margin + hdr + 210}" width="{(sidebar_w - 36) // 2}" height="26" rx="4" class="ui-toggle" />',
        f'  <text x="{sidebar_x + 16 + (sidebar_w - 36) // 4}" y="{margin + hdr + 228}" text-anchor="middle" class="ui-sidebar-text" style="font-size:11px;">Круговая</text>',
        f'  <rect x="{sidebar_x + 20 + (sidebar_w - 36) // 2}" y="{margin + hdr + 210}" width="{(sidebar_w - 36) // 2}" height="26" rx="4" class="ui-toggle" />',
        f'  <text x="{sidebar_x + 20 + 3 * (sidebar_w - 36) // 4}" y="{margin + hdr + 228}" text-anchor="middle" class="ui-sidebar-text" style="font-size:11px;">Столбчатый</text>',
        f'  <rect x="{sidebar_x + 16}" y="{margin + hdr + 248}" width="{sidebar_w - 32}" height="34" rx="4" class="ui-toggle" />',
        f'  <text x="{sidebar_x + sidebar_w // 2}" y="{margin + hdr + 270}" text-anchor="middle" class="ui-sidebar-text" style="font-size:12px;">Создать DOCX</text>',
        f'  <rect x="{sidebar_x + 16}" y="{margin + hdr + 292}" width="{sidebar_w - 32}" height="34" rx="4" class="ui-toggle" />',
        f'  <text x="{sidebar_x + sidebar_w // 2}" y="{margin + hdr + 314}" text-anchor="middle" class="ui-sidebar-text" style="font-size:12px;">Сохранить summary</text>',
        f'  <text x="{sidebar_x + 16}" y="{margin + hdr + 352}" class="ui-sidebar-title">Артефакты</text>',
        f'  <rect x="{sidebar_x + 16}" y="{margin + hdr + 368}" width="{sidebar_w - 32}" height="54" rx="6" class="ui-source-card" />',
        f'  <rect x="{sidebar_x + 16}" y="{margin + hdr + 368}" width="6" height="54" rx="2" class="ui-source-stripe" />',
        f'  <text x="{sidebar_x + 34}" y="{margin + hdr + 392}" class="ui-source-label">PNG</text>',
        f'  <text x="{sidebar_x + 34}" y="{margin + hdr + 412}" class="ui-source-title" style="font-size:12px;">chart.png</text>',
        '</svg>',
    ])
    return "\n".join(svg)


def rf_scenario_1_svg() -> str:
    """Scenario 1: Review Flow client status card fills the whole illustration area."""
    w, h = 980, 540
    margin = 0
    card_x = margin
    card_w = w - margin * 2
    card_y = margin
    card_h = h - margin * 2
    pad = 32
    left_w = (card_w - pad * 3) // 2
    right_x = card_x + left_w + pad * 2 + 32
    right_w = left_w - 32
    left_x = card_x + pad
    svg = [
        f'<svg class="ui-illustration" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" aria-label="Клиентский портал Review Flow: проверка статуса обращения и опубликованный ответ">',
        # Main card fills the illustration area
        f'  <rect x="{card_x}" y="{card_y}" width="{card_w}" height="{card_h}" rx="8" class="ui-msg-bot" />',
        # LEFT COLUMN — form
        f'  <text x="{left_x}" y="{card_y + 34}" class="ui-main-title" style="font-size:20px;">Проверить статус обращения</text>',
        f'  <text x="{left_x}" y="{card_y + 64}" class="ui-sidebar-text" style="font-size:12px;">Введите номер обращения и email, указанный при</text>',
        f'  <text x="{left_x}" y="{card_y + 80}" class="ui-sidebar-text" style="font-size:12px;">отправке. Мы покажем текущий статус и опубликованный ответ.</text>',
        # Number input
        f'  <text x="{left_x}" y="{card_y + 120}" class="ui-table-header-text">Номер обращения *</text>',
        f'  <rect x="{left_x}" y="{card_y + 128}" width="{left_w}" height="36" rx="6" class="ui-input" />',
        f'  <text x="{left_x + 14}" y="{card_y + 152}" class="ui-input-text" style="fill: var(--text-primary); font-size:13px;">NL-00250112-001</text>',
        # Email input
        f'  <text x="{left_x}" y="{card_y + 186}" class="ui-table-header-text">Email *</text>',
        f'  <rect x="{left_x}" y="{card_y + 194}" width="{left_w}" height="36" rx="6" class="ui-input" />',
        f'  <text x="{left_x + 14}" y="{card_y + 218}" class="ui-input-text" style="fill: var(--text-primary); font-size:13px;">a.petrov@example.com</text>',
        # Green submit button
        f'  <rect x="{left_x}" y="{card_y + 246}" width="{left_w}" height="42" rx="6" class="ui-btn-primary" />',
        f'  <text x="{left_x + left_w // 2}" y="{card_y + 273}" text-anchor="middle" class="ui-btn-text" style="font-size:15px;">Проверить статус</text>',
        # Topic + score
        f'  <text x="{left_x}" y="{card_y + 316}" class="ui-table-header-text">ТЕМА</text>',
        f'  <text x="{left_x}" y="{card_y + 338}" class="ui-sidebar-text" style="font-size:14px; fill: var(--text-primary);">Доставка</text>',
        f'  <text x="{left_x}" y="{card_y + 372}" class="ui-table-header-text">ОЦЕНКА</text>',
        f'  <text x="{left_x}" y="{card_y + 394}" class="ui-sidebar-text" style="font-size:14px; fill: var(--text-primary);">2 из 5</text>',
        f'  <text x="{left_x}" y="{card_y + 428}" class="ui-table-header-text">ВАШ ОТЗЫВ</text>',
        f'  <text x="{left_x}" y="{card_y + 450}" class="ui-sidebar-text" style="font-size:13px; fill: var(--text-primary);">Ваш курьер был крайне груб, бросил коробку у двери.</text>',
        f'  <text x="{left_x}" y="{card_y + 470}" class="ui-sidebar-text" style="font-size:13px; fill: var(--text-primary);">Прошу принять меры!</text>',
        # Security hint
        f'  <text x="{left_x}" y="{card_y + card_h - 24}" class="ui-subtitle" style="font-size:11px;">🔒 Ваши данные защищены и не передаются третьим лицам</text>',
        # Divider
        f'  <line x1="{card_x + pad + left_w + pad + 8}" y1="{card_y + 24}" x2="{card_x + pad + left_w + pad + 8}" y2="{card_y + card_h - 24}" stroke="var(--border)" stroke-width="1" />',
        # RIGHT COLUMN — result
        f'  <text x="{right_x}" y="{card_y + 30}" class="ui-table-header-text">НАЙДЕНО ОБРАЩЕНИЕ</text>',
        f'  <rect x="{right_x}" y="{card_y + 40}" width="120" height="26" rx="4" class="ui-source-card" />',
        f'  <text x="{right_x + 60}" y="{card_y + 58}" text-anchor="middle" class="ui-source-title" style="font-size:12px;">NL-00250112-001</text>',
        f'  <text x="{right_x}" y="{card_y + 86}" class="ui-source-title" style="font-size:14px;">Ответ опубликован</text>',
        # Timeline steps with checkmarks
        f'  <circle cx="{right_x + 14}" cy="{card_y + 122}" r="9" fill="var(--accent)" />',
        f'  <path d="M{right_x + 9} {card_y + 122} l4 4 l8 -9" stroke="#ffffff" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round" />',
        f'  <text x="{right_x + 36}" y="{card_y + 127}" class="ui-sidebar-text" style="font-size:13px;">Обращение получено</text>',
        f'  <circle cx="{right_x + 14}" cy="{card_y + 154}" r="9" fill="var(--accent)" />',
        f'  <path d="M{right_x + 9} {card_y + 154} l4 4 l8 -9" stroke="#ffffff" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round" />',
        f'  <text x="{right_x + 36}" y="{card_y + 159}" class="ui-sidebar-text" style="font-size:13px;">Классификация и анализ</text>',
        f'  <circle cx="{right_x + 14}" cy="{card_y + 186}" r="9" fill="var(--accent)" />',
        f'  <path d="M{right_x + 9} {card_y + 186} l4 4 l8 -9" stroke="#ffffff" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round" />',
        f'  <text x="{right_x + 36}" y="{card_y + 191}" class="ui-sidebar-text" style="font-size:13px;">Формирование ответа</text>',
        f'  <circle cx="{right_x + 14}" cy="{card_y + 218}" r="9" fill="var(--accent)" />',
        f'  <path d="M{right_x + 9} {card_y + 218} l4 4 l8 -9" stroke="#ffffff" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round" />',
        f'  <text x="{right_x + 36}" y="{card_y + 223}" class="ui-sidebar-text" style="font-size:13px;">На модерации</text>',
        f'  <circle cx="{right_x + 14}" cy="{card_y + 250}" r="10" fill="#2563eb" />',
        f'  <text x="{right_x + 14}" y="{card_y + 255}" text-anchor="middle" style="font-size:12px; fill:#ffffff; font-weight:600;">5</text>',
        f'  <text x="{right_x + 36}" y="{card_y + 255}" class="ui-sidebar-text" style="font-size:13px;">Опубликовано</text>',
        # Success box
        f'  <rect x="{right_x}" y="{card_y + 288}" width="{right_w - 24}" height="86" rx="8" class="ui-status-published" />',
        f'  <text x="{right_x + 14}" y="{card_y + 314}" class="ui-status-text" style="font-size:14px; font-weight:600;">Спасибо за обратную связь!</text>',
        f'  <text x="{right_x + 14}" y="{card_y + 338}" class="ui-sidebar-text" style="font-size:13px;">Мы опубликовали ответ на ваше обращение.</text>',
        f'  <text x="{right_x + 14}" y="{card_y + 358}" class="ui-sidebar-text" style="font-size:13px;">Ниже — текст от компании.</text>',
        # Company answer
        f'  <text x="{right_x}" y="{card_y + 394}" class="ui-table-header-text">ОТВЕТ КОМПАНИИ</text>',
        f'  <text x="{right_x}" y="{card_y + 418}" class="ui-sidebar-text" style="font-size:13px; fill: var(--text-primary);">Здравствуйте, Александр! Нам очень жаль,</text>',
        f'  <text x="{right_x}" y="{card_y + 438}" class="ui-sidebar-text" style="font-size:13px; fill: var(--text-primary);">что доставка оставила неприятное впечатление.</text>',
        f'  <text x="{right_x}" y="{card_y + 458}" class="ui-sidebar-text" style="font-size:13px; fill: var(--text-primary);">Мы зафиксировали ваше обращение и передали</text>',
        f'  <text x="{right_x}" y="{card_y + 478}" class="ui-sidebar-text" style="font-size:13px; fill: var(--text-primary);">его на рассмотрение службы доставки.</text>',
        f'  <text x="{right_x}" y="{card_y + card_h - 30}" class="ui-sidebar-text" style="font-size:12px; fill: var(--text-muted);">◯ Мы ценим ваше доверие</text>',
        '</svg>',
    ]
    return "\n".join(svg)


def rf_scenario_2_svg() -> str:
    """Scenario 2: Review Flow operator console — HITL review card."""
    w, h = 980, 540
    margin, hdr = 14, 56
    inner_h = h - margin * 2 - hdr
    sidebar_w = 210
    main_x = margin + sidebar_w + 12
    main_w = w - margin * 2 - sidebar_w - 12
    svg = [
        f'<svg class="ui-illustration" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" aria-label="Операторская консоль Review Flow: очередь обращений и HITL-проверка">',
        '  <defs>',
        '    <clipPath id="rf-oper-clip">',
        f'      <rect x="{margin}" y="{margin}" width="{w - margin * 2}" height="{h - margin * 2}" rx="6" />',
        '    </clipPath>',
        '  </defs>',
        # Window + header
        f'  <rect x="{margin}" y="{margin}" width="{w - margin * 2}" height="{h - margin * 2}" rx="6" class="ui-window" />',
        f'  <rect x="{margin}" y="{margin}" width="{w - margin * 2}" height="{hdr}" class="ui-header" clip-path="url(#rf-oper-clip)" />',
        f'  <circle cx="42" cy="{margin + hdr // 2}" r="14" class="ui-avatar" />',
        f'  <text x="66" y="{margin + 30}" class="ui-title">Review Flow Operations</text>',
        f'  <text x="{w - margin - 18}" y="{margin + 34}" text-anchor="end" class="ui-subtitle" style="font-size:13px; fill: var(--accent); font-weight:500;">Zerocoder</text>',
        # Sidebar
        f'  <rect x="{margin}" y="{margin + hdr}" width="{sidebar_w}" height="{inner_h}" class="ui-sidebar" clip-path="url(#rf-oper-clip)" />',
        f'  <text x="{margin + 18}" y="{margin + hdr + 28}" class="ui-sidebar-title">Операции</text>',
        f'  <rect x="{margin + 12}" y="{margin + hdr + 44}" width="{sidebar_w - 24}" height="34" rx="4" class="ui-sidebar-item-active" />',
        f'  <text x="{margin + 26}" y="{margin + hdr + 66}" class="ui-sidebar-text-active">Очередь обращений</text>',
        f'  <rect x="{margin + 12}" y="{margin + hdr + 86}" width="{sidebar_w - 24}" height="28" rx="4" class="ui-sidebar-item" />',
        f'  <text x="{margin + 26}" y="{margin + hdr + 105}" class="ui-sidebar-text">Типовые ситуации</text>',
        f'  <rect x="{margin + 12}" y="{margin + hdr + 122}" width="{sidebar_w - 24}" height="28" rx="4" class="ui-sidebar-item" />',
        f'  <text x="{margin + 26}" y="{margin + hdr + 141}" class="ui-sidebar-text">Кандидаты</text>',
        f'  <rect x="{margin + 12}" y="{margin + hdr + inner_h - 46}" width="{sidebar_w - 24}" height="32" rx="4" class="ui-toggle" />',
        f'  <text x="{margin + sidebar_w // 2}" y="{margin + hdr + inner_h - 25}" text-anchor="middle" class="ui-sidebar-text">Выйти</text>',
        # Main: header + filters
        f'  <text x="{main_x + 18}" y="{margin + hdr + 36}" class="ui-main-title">Очередь обращений</text>',
        f'  <text x="{main_x + 18}" y="{margin + hdr + 60}" class="ui-subtitle">Журнал модерации</text>',
    ]
    filters = [("все статусы", 100), ("приоритет", 100), ("сценарий", 100), ("тональность", 100)]
    fx = main_x + 18
    for label, fw in filters:
        svg.extend([
            f'  <rect x="{fx}" y="{margin + hdr + 76}" width="{fw}" height="28" rx="4" class="ui-toggle" />',
            f'  <text x="{fx + fw // 2}" y="{margin + hdr + 95}" text-anchor="middle" class="ui-sidebar-text" style="font-size:12px;">{label}</text>',
        ])
        fx += fw + 8
    # Queue list (left column inside main)
    list_w = (main_w - 48) // 3
    list_x = main_x + 18
    queue_y = margin + hdr + 118
    queue_items = [
        ("NL-00250012-001", "На проверке", "Ваш курьер был крайне груб..."),
        ("NL-00250010-001", "На проверке", "Здравствуйте! Курьер опоздал..."),
        ("NL-00250009-003", "Одобрено", "Какую прибыль вы получили в..."),
    ]
    for num, status, preview in queue_items:
        active = "На проверке" in status
        cls = "ui-sidebar-item-active" if active else "ui-sidebar-item"
        svg.extend([
            f'  <rect x="{list_x}" y="{queue_y}" width="{list_w}" height="70" rx="6" class="{cls}" />',
            f'  <text x="{list_x + 12}" y="{queue_y + 20}" class="ui-sidebar-text" style="font-size:12px; font-weight:600;">{num}</text>',
            f'  <text x="{list_x + list_w - 12}" y="{queue_y + 20}" text-anchor="end" class="ui-status-text" style="font-size:11px;">{status}</text>' if active else f'  <text x="{list_x + list_w - 12}" y="{queue_y + 20}" text-anchor="end" class="ui-sidebar-text" style="font-size:11px;">{status}</text>',
            f'  <text x="{list_x + 12}" y="{queue_y + 40}" class="ui-sidebar-text" style="font-size:12px;">{preview[:38]}...</text>',
        ])
        queue_y += 82
    # Detail card (right 2/3 of main)
    detail_x = list_x + list_w + 16
    detail_w = main_w - list_w - 40
    detail_y = margin + hdr + 118
    detail_h = inner_h - 126
    svg.extend([
        f'  <rect x="{detail_x}" y="{detail_y}" width="{detail_w}" height="{detail_h}" rx="6" class="ui-window" />',
        f'  <text x="{detail_x + 18}" y="{detail_y + 30}" class="ui-main-title">ОБРАЩЕНИЕ {queue_items[0][0]}</text>',
        f'  <rect x="{detail_x + detail_w - 110}" y="{detail_y + 12}" width="92" height="28" rx="4" class="ui-status-published" />',
        f'  <text x="{detail_x + detail_w - 64}" y="{detail_y + 31}" text-anchor="middle" class="ui-status-text" style="font-size:12px;">ОДОБРЕНО</text>',
    ])
    # Left block: request details
    left_block_x = detail_x + 18
    left_block_w = (detail_w - 48) // 2
    left_block_y = detail_y + 52
    svg.extend([
        f'  <text x="{left_block_x}" y="{left_block_y}" class="ui-table-header-text">ОБРАЩЕНИЕ КЛИЕНТА</text>',
        f'  <rect x="{left_block_x}" y="{left_block_y + 12}" width="{left_block_w}" height="70" rx="6" class="ui-msg-bot" />',
        f'  <text x="{left_block_x + 14}" y="{left_block_y + 38}" class="ui-sidebar-text" style="font-size:12px;">Ваш курьер был крайне груб,</text>',
        f'  <text x="{left_block_x + 14}" y="{left_block_y + 56}" class="ui-sidebar-text" style="font-size:12px;">бросил коробку у двери.</text>',
    ])
    # Right block: selected Response Case
    right_block_x = left_block_x + left_block_w + 12
    right_block_y = left_block_y
    right_block_w = left_block_w
    svg.extend([
        f'  <text x="{right_block_x}" y="{right_block_y}" class="ui-table-header-text">ВЫБРАННАЯ ТИПОВАЯ СИТУАЦИЯ</text>',
        f'  <rect x="{right_block_x}" y="{right_block_y + 12}" width="{right_block_w}" height="70" rx="6" class="ui-source-card" />',
        f'  <text x="{right_block_x + 14}" y="{right_block_y + 32}" class="ui-source-title" style="font-size:13px;">Жалоба на курьера</text>',
        f'  <text x="{right_block_x + 14}" y="{right_block_y + 52}" class="ui-sidebar-text" style="font-size:12px;">Confidence: низкая</text>',
        f'  <text x="{right_block_x + 14}" y="{right_block_y + 68}" class="ui-sidebar-text" style="font-size:11px;">0.65 (порог ТС: 0.85)</text>',
    ])
    # Approved basis + LLM draft below
    draft_y = left_block_y + 122
    svg.extend([
        f'  <text x="{left_block_x}" y="{draft_y}" class="ui-table-header-text">УТВЕРЖДЁННАЯ ОСНОВА ОТВЕТА</text>',
        f'  <rect x="{left_block_x}" y="{draft_y + 12}" width="{left_block_w}" height="94" rx="6" class="ui-msg-bot" />',
        f'  <text x="{left_block_x + 14}" y="{draft_y + 40}" class="ui-sidebar-text" style="font-size:12px;">Здравствуйте! Нам очень жаль,</text>',
        f'  <text x="{left_block_x + 14}" y="{draft_y + 58}" class="ui-sidebar-text" style="font-size:12px;">что доставка оставила</text>',
        f'  <text x="{left_block_x + 14}" y="{draft_y + 76}" class="ui-sidebar-text" style="font-size:12px;">неприятное впечатление</text>',
        f'  <text x="{right_block_x}" y="{draft_y}" class="ui-table-header-text">ОТВЕТ LLM</text>',
        f'  <rect x="{right_block_x}" y="{draft_y + 12}" width="{right_block_w}" height="94" rx="6" class="ui-source-card" />',
        f'  <text x="{right_block_x + 14}" y="{draft_y + 40}" class="ui-sidebar-text" style="font-size:12px;">Здравствуйте, Александр!</text>',
        f'  <text x="{right_block_x + 14}" y="{draft_y + 58}" class="ui-sidebar-text" style="font-size:12px;">Нам очень жаль, что доставка</text>',
        f'  <text x="{right_block_x + 14}" y="{draft_y + 76}" class="ui-sidebar-text" style="font-size:12px;">оставила неприятное впечат...</text>',
    ])
    # Action buttons
    btn_y = detail_y + detail_h - 44
    svg.extend([
        f'  <rect x="{detail_x + 18}" y="{btn_y}" width="120" height="36" rx="4" class="ui-btn-primary" />',
        f'  <text x="{detail_x + 78}" y="{btn_y + 23}" text-anchor="middle" class="ui-btn-text">Опубликовать</text>',
        f'  <rect x="{detail_x + 150}" y="{btn_y}" width="110" height="36" rx="4" class="ui-toggle" />',
        f'  <text x="{detail_x + 205}" y="{btn_y + 23}" text-anchor="middle" class="ui-sidebar-text" style="font-size:12px;">Эскалировать</text>',
        f'  <rect x="{detail_x + 272}" y="{btn_y}" width="110" height="36" rx="4" class="ui-toggle" />',
        f'  <text x="{detail_x + 327}" y="{btn_y + 23}" text-anchor="middle" class="ui-sidebar-text" style="font-size:12px;">Редактировать</text>',
    ])
    svg.append('</svg>')
    return "\n".join(svg)


def ada_scenario_2_svg() -> str:
    """Scenario 2: /admin — runtime config fills the full illustration area."""
    w, h = 980, 540
    margin, hdr = 14, 56
    inner_h = h - margin * 2 - hdr
    # Two-column layout like the real admin screenshot, filling area
    left_w = (w - margin * 2 - 16) // 2
    right_w = w - margin * 2 - 16 - left_w
    left_x, right_x = margin, margin + left_w + 16
    svg = [
        f'<svg class="ui-illustration" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" aria-label="Админка оператора Data Assistant: runtime-конфиг, системный промпт и реестры агента">',
        '  <defs>',
        '    <clipPath id="ada-admin-clip">',
        f'      <rect x="{margin}" y="{margin}" width="{w - margin * 2}" height="{h - margin * 2}" rx="6" />',
        '    </clipPath>',
        '  </defs>',
        # Window + header
        f'  <rect x="{margin}" y="{margin}" width="{w - margin * 2}" height="{h - margin * 2}" rx="6" class="ui-window" />',
        f'  <rect x="{margin}" y="{margin}" width="{w - margin * 2}" height="{hdr}" class="ui-header" clip-path="url(#ada-admin-clip)" />',
        f'  <circle cx="42" cy="{margin + hdr // 2}" r="14" class="ui-avatar" />',
        f'  <text x="66" y="{margin + 30}" class="ui-title">AI Data Chat</text>',
        f'  <text x="66" y="{margin + 48}" class="ui-subtitle" style="font-size:12px;">чат для файлов, графиков и отчётов</text>',
        # Main title + save button
        f'  <text x="{margin + 16}" y="{margin + hdr + 28}" class="ui-main-title">Админка оператора</text>',
        f'  <text x="{margin + 16}" y="{margin + hdr + 50}" class="ui-subtitle">Runtime-параметры применяются на следующем запросе — без рестарта.</text>',
        f'  <rect x="{w - margin - 150}" y="{margin + hdr + 14}" width="135" height="32" rx="4" class="ui-btn-primary" />',
        f'  <text x="{w - margin - 82}" y="{margin + hdr + 35}" text-anchor="middle" class="ui-btn-text" style="font-size:13px;">Сохранить</text>',
        # Usage stats row (5 cards across full width)
    ]
    stats = [("Запросов", "14"), ("Ошибок", "0"), ("Токенов всего", "47 988"), ("Промпт", "34 317"), ("Комплит", "13 671")]
    stat_w = (w - margin * 2 - 16) // 5
    for i, (label, value) in enumerate(stats):
        bx = margin + i * (stat_w + 4)
        svg.extend([
            f'  <rect x="{bx}" y="{margin + hdr + 66}" width="{stat_w}" height="52" rx="6" class="ui-window" />',
            f'  <text x="{bx + stat_w // 2}" y="{margin + hdr + 94}" text-anchor="middle" class="ui-main-title" style="font-size:18px;">{value}</text>',
            f'  <text x="{bx + stat_w // 2}" y="{margin + hdr + 112}" text-anchor="middle" class="ui-subtitle" style="font-size:11px;">{label}</text>',
        ])
    # Left card: system prompt (tall)
    card_top = margin + hdr + 128
    card_h = inner_h - 128 - 8
    svg.extend([
        f'  <rect x="{left_x}" y="{card_top}" width="{left_w}" height="{card_h}" rx="6" class="ui-window" />',
        f'  <text x="{left_x + 18}" y="{card_top + 30}" class="ui-main-title">Системный промпт</text>',
        f'  <text x="{left_x + 18}" y="{card_top + 52}" class="ui-subtitle">/app/prompts/v1/system.md</text>',
    ])
    lines = 12
    line_h = (card_h - 80) // lines
    for i in range(lines):
        svg.append(f'  <rect x="{left_x + 18}" y="{card_top + 70 + i * line_h}" width="{left_w - 36}" height="{line_h - 6}" rx="4" class="ui-input" />')
    # Right card: runtime config fills the whole right column
    right_top_h = card_h - 16
    svg.extend([
        f'  <rect x="{right_x}" y="{card_top}" width="{right_w}" height="{right_top_h}" rx="6" class="ui-window" />',
        f'  <text x="{right_x + 18}" y="{card_top + 30}" class="ui-main-title">Runtime-конфиг</text>',
        f'  <text x="{right_x + 18}" y="{card_top + 52}" class="ui-subtitle">/app/storage/config.json</text>',
    ])
    # Provider preset tabs
    tab_w = (right_w - 18 * 2 - 12) // 4
    for i, name in enumerate(["OpenAI", "GigaChat", "YandexGPT", "Свой"]):
        tx = right_x + 18 + i * (tab_w + 4)
        active = name == "GigaChat"
        cls = "ui-toggle-active" if active else "ui-toggle"
        tcls = "ui-toggle-text" if active else "ui-toggle-text-inactive"
        svg.extend([
            f'  <rect x="{tx}" y="{card_top + 68}" width="{tab_w}" height="30" rx="4" class="{cls}" />',
            f'  <text x="{tx + tab_w // 2}" y="{card_top + 88}" text-anchor="middle" class="{tcls}" style="font-size:12px;">{name}</text>',
        ])
    # Fields
    fields = [
        ("Имя провайдера", "GigaChat"),
        ("Модель", "GigaChat-Max"),
        ("Endpoint (base_url)", "https://gigachat.devices.sberbank.ru/api/v1"),
    ]
    field_y = card_top + 112
    for label, value in fields:
        svg.extend([
            f'  <text x="{right_x + 18}" y="{field_y}" class="ui-table-header-text" style="font-size:12px;">{label}</text>',
            f'  <rect x="{right_x + 18}" y="{field_y + 8}" width="{right_w - 36}" height="28" rx="4" class="ui-input" />',
            f'  <text x="{right_x + 32}" y="{field_y + 26}" class="ui-input-text" style="fill: var(--text-primary);">{value}</text>',
        ])
        field_y += 54
    # Runtime config card ends here; no agent registries block per UX decision.
    svg.append('</svg>')
    return "\n".join(svg)


def rar_scenario_1_svg() -> str:
    """Scenario 1: public review site — form on the left, review thread with AI Support replies on the right."""
    w, h = 980, 620
    margin = 14
    hdr = 54
    inner_h = h - margin * 2 - hdr
    form_w = 250
    thread_x = margin + form_w + 16
    thread_w = w - margin * 2 - form_w - 16

    # Card geometry
    card_x = thread_x + 12
    card_w = thread_w - 24
    reply_x = thread_x + 36
    reply_w = thread_w - 60
    badge_h = 18
    status_w = 72
    tone_w = 78
    gap = 10

    # Right-aligned badge pair inside a card of given width
    def badge_pair(cx, cw, cy):
        right = cx + cw - 12
        tone_x = right - tone_w
        status_x = tone_x - 8 - status_w
        return (
            f'  <rect x="{status_x}" y="{cy}" width="{status_w}" height="{badge_h}" rx="3" class="ui-status-published" />',
            f'  <text x="{status_x + status_w // 2}" y="{cy + 14}" text-anchor="middle" class="ui-status-text" style="font-size:10px;">обработан</text>',
            f'  <rect x="{tone_x}" y="{cy}" width="{tone_w}" height="{badge_h}" rx="3" class="ui-input" />',
            f'  <text x="{tone_x + tone_w // 2}" y="{cy + 14}" text-anchor="middle" class="ui-input-text" style="font-size:10px;">нейтральный</text>',
        )

    svg = [
        f'<svg class="ui-illustration" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" aria-label="Сайт отзывов Review Auto Responder: форма слева, тред с AI-ответами справа">',
        '  <defs>',
        f'    <clipPath id="rar-site-clip">',
        f'      <rect x="{margin}" y="{margin}" width="{w - margin * 2}" height="{h - margin * 2}" rx="6" />',
        '    </clipPath>',
        '  </defs>',
        # window + header
        f'  <rect x="{margin}" y="{margin}" width="{w - margin * 2}" height="{h - margin * 2}" rx="6" class="ui-window" />',
        f'  <rect x="{margin}" y="{margin}" width="{w - margin * 2}" height="{hdr}" class="ui-header" clip-path="url(#rar-site-clip)" />',
        f'  <text x="{margin + 18}" y="{margin + 34}" class="ui-title">Форма отзывов</text>',
        f'  <text x="{margin + 18}" y="{margin + 48}" class="ui-subtitle" style="font-size:11px;">Оставьте отзыв, система подготовит ответ автоматически</text>',
        # form panel (left)
        f'  <rect x="{margin}" y="{margin + hdr}" width="{form_w}" height="{inner_h}" fill="var(--bg)" clip-path="url(#rar-site-clip)" />',
        f'  <rect x="{margin + 16}" y="{margin + hdr + 18}" width="{form_w - 32}" height="36" rx="4" class="ui-input" />',
        f'  <text x="{margin + 28}" y="{margin + hdr + 42}" class="ui-input-text" style="font-size:12px;">Имя (необязательно)</text>',
        f'  <rect x="{margin + 16}" y="{margin + hdr + 70}" width="{form_w - 32}" height="96" rx="4" class="ui-input" />',
        f'  <text x="{margin + 28}" y="{margin + hdr + 104}" class="ui-input-text" style="font-size:12px;">Напишите ваш отзыв</text>',
        f'  <rect x="{margin + 16}" y="{margin + hdr + 182}" width="{form_w - 32}" height="40" rx="6" class="ui-btn-primary" />',
        f'  <text x="{margin + form_w // 2}" y="{margin + hdr + 208}" text-anchor="middle" class="ui-btn-text" style="font-size:14px;">Отправить</text>',
        f'  <rect x="{margin + 16}" y="{margin + hdr + 238}" width="{form_w - 32}" height="28" rx="4" class="ui-source-card" />',
        f'  <text x="{margin + 28}" y="{margin + hdr + 258}" class="ui-sidebar-text" style="font-size:11px;">Демо: осталось 5 из 5</text>',
        # thread panel (right)
        f'  <rect x="{thread_x}" y="{margin + hdr}" width="{thread_w}" height="{inner_h}" class="ui-sidebar" clip-path="url(#rar-site-clip)" />',
    ]

    # Card 1: review by Аноним
    c1_y = margin + hdr + 16
    c1_h = 74
    svg.extend([
        f'  <rect x="{card_x}" y="{c1_y}" width="{card_w}" height="{c1_h}" rx="6" class="ui-window" />',
        f'  <text x="{card_x + 16}" y="{c1_y + 24}" class="ui-sidebar-title" style="font-size:13px;">Аноним · 14.08.2026, 04:14:35</text>',
    ])
    svg.extend(badge_pair(card_x, card_w, c1_y + 10))
    svg.append(
        f'  <text x="{card_x + 16}" y="{c1_y + 54}" class="ui-msg-text-bot" style="font-size:12px;">Прислали посылку с повреждённой упаковкой! Срочно нужна замена!!!</text>'
    )

    # Card 2: AI Support reply to Аноним
    c2_y = c1_y + c1_h + gap
    c2_h = 110
    svg.extend([
        f'  <rect x="{reply_x}" y="{c2_y}" width="{reply_w}" height="{c2_h}" rx="6" class="ui-msg-bot" />',
        f'  <text x="{reply_x + 16}" y="{c2_y + 24}" class="ui-sidebar-title" style="font-size:13px;">AI Support · 14.08.2026, 04:14:38</text>',
    ])
    svg.extend(badge_pair(reply_x, reply_w, c2_y + 10))
    svg.extend([
        f'  <text x="{reply_x + 16}" y="{c2_y + 58}" class="ui-msg-text-bot" style="font-size:12px;">Нам очень жаль, что так произошло. Мы немедленно отправим вам замену.</text>',
        f'  <text x="{reply_x + 16}" y="{c2_y + 78}" class="ui-msg-text-bot" style="font-size:12px;">Пожалуйста, сообщите нам номер вашего заказа для быстрой обработки запроса.</text>',
    ])

    # Card 3: review by Александр
    c3_y = c2_y + c2_h + gap
    c3_h = 90
    svg.extend([
        f'  <rect x="{card_x}" y="{c3_y}" width="{card_w}" height="{c3_h}" rx="6" class="ui-window" />',
        f'  <text x="{card_x + 16}" y="{c3_y + 24}" class="ui-sidebar-title" style="font-size:13px;">Александр · 14.08.2026, 04:13:41</text>',
    ])
    svg.extend(badge_pair(card_x, card_w, c3_y + 10))
    svg.extend([
        f'  <text x="{card_x + 16}" y="{c3_y + 54}" class="ui-msg-text-bot" style="font-size:12px;">Курьер вашей компании был крайне груб, бросил посылку возле дверей, на замечания</text>',
        f'  <text x="{card_x + 16}" y="{c3_y + 74}" class="ui-msg-text-bot" style="font-size:12px;">отреагировал резко. Прошу принять меры!!!</text>',
    ])

    # Card 4: AI Support reply to Александр
    c4_y = c3_y + c3_h + gap
    c4_h = 110
    svg.extend([
        f'  <rect x="{reply_x}" y="{c4_y}" width="{reply_w}" height="{c4_h}" rx="6" class="ui-msg-bot" />',
        f'  <text x="{reply_x + 16}" y="{c4_y + 24}" class="ui-sidebar-title" style="font-size:13px;">AI Support · 14.08.2026, 04:13:47</text>',
    ])
    svg.extend(badge_pair(reply_x, reply_w, c4_y + 10))
    svg.extend([
        f'  <text x="{reply_x + 16}" y="{c4_y + 58}" class="ui-msg-text-bot" style="font-size:12px;">Нам очень жаль, что вы столкнулись с таким отношением.</text>',
        f'  <text x="{reply_x + 16}" y="{c4_y + 78}" class="ui-msg-text-bot" style="font-size:12px;">Мы обязательно разберёмся в ситуации и примем соответствующие меры. Пожалуйста,</text>',
        f'  <text x="{reply_x + 16}" y="{c4_y + 98}" class="ui-msg-text-bot" style="font-size:12px;">сообщите нам детали вашего заказа для оперативного решения вопроса.</text>',
    ])

    svg.append('</svg>')
    return "\n".join(svg)


def rar_scenario_2_svg() -> str:
    """Scenario 2: /admin execution detail panel for the auto-responded review."""
    w, h = 980, 470
    margin = 20
    hdr = 52
    inner_h = h - margin * 2 - hdr
    pad = 18
    gap = 16

    svg = [
        f'<svg class="ui-illustration" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" aria-label="Review Auto Responder: админка детализации выполнения запроса">',
        '  <defs>',
        f'    <clipPath id="rar-admin-clip">',
        f'      <rect x="{margin}" y="{margin}" width="{w - margin * 2}" height="{h - margin * 2}" rx="8" />',
        '    </clipPath>',
        '  </defs>',
        # window + header
        f'  <rect x="{margin}" y="{margin}" width="{w - margin * 2}" height="{h - margin * 2}" rx="8" class="ui-window" />',
        f'  <rect x="{margin}" y="{margin}" width="{w - margin * 2}" height="{hdr}" class="ui-header" clip-path="url(#rar-admin-clip)" />',
        f'  <text x="{margin + pad}" y="{margin + 34}" class="ui-main-title" style="font-size:16px;">ДЕТАЛИЗАЦИЯ ЗАПРОСА</text>',
        # success badge
        f'  <rect x="{w - margin - 100}" y="{margin + 16}" width="86" height="22" rx="4" class="ui-status-published" />',
        f'  <text x="{w - margin - 57}" y="{margin + 31}" text-anchor="middle" class="ui-status-text" style="font-size:10px;">УСПЕШНО</text>',
        # content background
        f'  <rect x="{margin + 12}" y="{margin + hdr}" width="{w - margin * 2 - 24}" height="{inner_h}" fill="var(--bg)" clip-path="url(#rar-admin-clip)" />',
    ]

    y = margin + hdr + pad
    col_w = (w - margin * 2 - 24 - gap - pad * 2) // 2
    left_x = margin + pad + 12
    right_x = left_x + col_w + gap

    # --- Request params ---
    rp_h = 130
    svg.extend([
        f'  <rect x="{left_x}" y="{y}" width="{col_w}" height="{rp_h}" rx="6" class="ui-window" />',
        f'  <text x="{left_x + 12}" y="{y + 22}" class="ui-table-header-text">ПАРАМЕТРЫ ЗАПРОСА</text>',
        f'  <text x="{left_x + 12}" y="{y + 44}" class="ui-sidebar-text" style="font-size:12px;">Код отзыва</text>',
        f'  <text x="{left_x + 120}" y="{y + 44}" class="ui-sidebar-text" style="font-size:12px; font-weight:500; fill: var(--text-primary);">#56</text>',
        f'  <text x="{left_x + 12}" y="{y + 62}" class="ui-sidebar-text" style="font-size:12px;">Имя пользователя</text>',
        f'  <text x="{left_x + 140}" y="{y + 62}" class="ui-sidebar-text" style="font-size:12px; font-weight:500; fill: var(--text-primary);">—</text>',
        f'  <text x="{left_x + 12}" y="{y + 80}" class="ui-sidebar-text" style="font-size:12px;">Тон</text>',
        f'  <rect x="{left_x + 140}" y="{y + 68}" width="86" height="16" rx="3" class="ui-input" />',
        f'  <text x="{left_x + 183}" y="{y + 80}" text-anchor="middle" class="ui-input-text" style="font-size:10px;">нейтральный</text>',
        f'  <text x="{left_x + 12}" y="{y + 98}" class="ui-sidebar-text" style="font-size:12px;">Маршрут</text>',
        f'  <text x="{left_x + 140}" y="{y + 98}" class="ui-sidebar-text" style="font-size:12px; font-weight:500; fill: var(--text-primary);">review_processing</text>',
        f'  <text x="{left_x + 12}" y="{y + 116}" class="ui-sidebar-text" style="font-size:12px;">Время создания</text>',
        f'  <text x="{left_x + 140}" y="{y + 116}" class="ui-sidebar-text" style="font-size:12px; font-weight:500; fill: var(--text-primary);">2026-08-14 04:14:35</text>',
    ])

    # --- Execution params ---
    ep_h = 130
    svg.extend([
        f'  <rect x="{right_x}" y="{y}" width="{col_w}" height="{ep_h}" rx="6" class="ui-window" />',
        f'  <text x="{right_x + 12}" y="{y + 22}" class="ui-table-header-text">ПАРАМЕТРЫ ИСПОЛНЕНИЯ</text>',
        f'  <text x="{right_x + 12}" y="{y + 44}" class="ui-sidebar-text" style="font-size:12px;">Провайдер</text>',
        f'  <text x="{right_x + 130}" y="{y + 44}" class="ui-sidebar-text" style="font-size:12px; font-weight:500; fill: var(--text-primary);">gigachat</text>',
        f'  <text x="{right_x + 12}" y="{y + 62}" class="ui-sidebar-text" style="font-size:12px;">Модель</text>',
        f'  <text x="{right_x + 130}" y="{y + 62}" class="ui-sidebar-text" style="font-size:12px; font-weight:500; fill: var(--text-primary);">GigaChat-Max</text>',
        f'  <text x="{right_x + 12}" y="{y + 80}" class="ui-sidebar-text" style="font-size:12px;">Длительность</text>',
        f'  <text x="{right_x + 130}" y="{y + 80}" class="ui-sidebar-text" style="font-size:12px; font-weight:500; fill: var(--text-primary);">1437 мс</text>',
        f'  <text x="{right_x + 12}" y="{y + 98}" class="ui-sidebar-text" style="font-size:12px;">Токены</text>',
        f'  <text x="{right_x + 130}" y="{y + 98}" class="ui-sidebar-text" style="font-size:12px; font-weight:500; fill: var(--text-primary);">212</text>',
        f'  <text x="{right_x + 12}" y="{y + 116}" class="ui-sidebar-text" style="font-size:12px;">Время завершения</text>',
        f'  <text x="{right_x + 130}" y="{y + 116}" class="ui-sidebar-text" style="font-size:12px; font-weight:500; fill: var(--text-primary);">2026-08-14 04:14:39</text>',
    ])

    y += rp_h + gap

    # --- Pipeline chain ---
    chain_h = 56
    svg.extend([
        f'  <rect x="{left_x}" y="{y}" width="{col_w * 2 + gap}" height="{chain_h}" rx="6" class="ui-window" />',
        f'  <text x="{left_x + 12}" y="{y + 22}" class="ui-table-header-text">ЦЕПОЧКА ЭТАПОВ</text>',
        f'  <text x="{left_x + 12}" y="{y + 42}" class="ui-sidebar-text" style="font-size:11px;">Получен отзыв → Классификация тона → Уведомление Telegram → Генерация LLM → Сохранение ответа → Отметка обработано</text>',
    ])

    y += chain_h + gap

    # --- User request ---
    ur_h = 120
    svg.extend([
        f'  <rect x="{left_x}" y="{y}" width="{col_w}" height="{ur_h}" rx="6" class="ui-window" />',
        f'  <text x="{left_x + 12}" y="{y + 22}" class="ui-table-header-text">ЗАПРОС ПОЛЬЗОВАТЕЛЯ</text>',
        f'  <text x="{left_x + 12}" y="{y + 52}" class="ui-msg-text-bot" style="font-size:12px;">Прислали посылку с повреждённой упаковкой!</text>',
        f'  <text x="{left_x + 12}" y="{y + 74}" class="ui-msg-text-bot" style="font-size:12px;">Срочно нужна замена!!!</text>',
    ])

    # --- System response ---
    sr_h = 120
    svg.extend([
        f'  <rect x="{right_x}" y="{y}" width="{col_w}" height="{sr_h}" rx="6" class="ui-window" />',
        f'  <text x="{right_x + 12}" y="{y + 22}" class="ui-table-header-text">ОТВЕТ СИСТЕМЫ</text>',
        f'  <text x="{right_x + 12}" y="{y + 50}" class="ui-msg-text-bot" style="font-size:12px;">Нам очень жаль, что так произошло. Мы немедленно отправим</text>',
        f'  <text x="{right_x + 12}" y="{y + 72}" class="ui-msg-text-bot" style="font-size:12px;">вам замену. Пожалуйста, сообщите нам номер вашего заказа</text>',
        f'  <text x="{right_x + 12}" y="{y + 94}" class="ui-msg-text-bot" style="font-size:12px;">для быстрой обработки запроса.</text>',
    ])

    svg.append('</svg>')
    return "\n".join(svg)


def hr_scenario_2_svg() -> str:
    """HR console candidate card."""
    w, h = 980, 620
    svg = [
        f'<svg class="ui-illustration" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" aria-label="HR Assistant: карточка кандидата с match score и решением">',
        '  <defs>',
        '    <clipPath id="hr-window-clip">',
        f'      <rect x="20" y="10" width="{w-40}" height="{h-20}" rx="8" />',
        '    </clipPath>',
        '  </defs>',
        f'  <rect x="20" y="10" width="{w-40}" height="{h-20}" rx="8" class="ui-window" />',
        f'  <rect x="20" y="10" width="{w-40}" height="58" class="ui-header" clip-path="url(#hr-window-clip)" />',
        '  <text x="40" y="42" class="ui-title">HR Assistant · Консоль рекрутера</text>',
        '  <text x="700" y="42" class="ui-subtitle">PostgreSQL SOT · LLM matching</text>',
        # sidebar
        '  <rect x="20" y="68" width="210" height="552" class="ui-sidebar" clip-path="url(#hr-window-clip)" />',
        '  <text x="40" y="100" class="ui-sidebar-title">Кандидаты</text>',
        '  <rect x="40" y="120" width="170" height="32" rx="4" class="ui-sidebar-item-active" />',
        '  <text x="56" y="141" class="ui-sidebar-text-active">Иванов Иван</text>',
        '  <rect x="40" y="162" width="170" height="32" rx="4" class="ui-sidebar-item" />',
        '  <text x="56" y="183" class="ui-sidebar-text">Петрова Мария</text>',
        # card
        '  <rect x="260" y="90" width="680" height="510" rx="6" class="ui-window" />',
        '  <text x="286" y="130" class="ui-main-title">Иванов Иван — ML Engineer</text>',
        '  <text x="286" y="156" class="ui-subtitle">Вакансия: Senior ML Engineer · Team AI</text>',
        # match score
        '  <rect x="286" y="190" width="180" height="80" rx="6" class="ui-source-card" />',
        '  <text x="306" y="220" class="ui-source-label">MATCH SCORE</text>',
        '  <text x="306" y="256" class="ui-main-title">92/100</text>',
        # decision
        '  <rect x="490" y="190" width="180" height="80" rx="6" class="ui-status-published" />',
        '  <text x="510" y="220" class="ui-source-label">РЕШЕНИЕ</text>',
        '  <text x="510" y="256" class="ui-status-text">Пригласить</text>',
        # reasons
        '  <text x="286" y="310" class="ui-sidebar-title">Причины решения</text>',
        '  <rect x="286" y="330" width="618" height="36" rx="4" class="ui-input" />',
        '  <text x="302" y="354" class="ui-input-text" style="fill:var(--text-primary);">✓ Опыт Python / ML 5+ лет</text>',
        '  <rect x="286" y="374" width="618" height="36" rx="4" class="ui-input" />',
        '  <text x="302" y="398" class="ui-input-text" style="fill:var(--text-primary);">✓ Проекты с LLM и RAG</text>',
        '  <rect x="286" y="418" width="618" height="36" rx="4" class="ui-input" />',
        '  <text x="302" y="442" class="ui-input-text" style="fill:var(--text-primary);">✓ Совпадение по стеку команды</text>',
        # buttons
        '  <rect x="286" y="540" width="180" height="40" rx="4" class="ui-btn-primary" />',
        '  <text x="376" y="565" text-anchor="middle" class="ui-btn-text">Назначить интервью</text>',
        '  <rect x="490" y="540" width="180" height="40" rx="4" class="ui-toggle" />',
        '  <text x="580" y="565" text-anchor="middle" class="ui-sidebar-text">Отклонить</text>',
        '</svg>',
    ]
    return "\n".join(svg)


def retail_metrics_svg() -> str:
    """Five key pilot metrics dashboard."""
    w, h = 980, 540
    metrics = [
        ("Снижение нагрузки", "40%", "на операторов 1-го уровня"),
        ("Время ответа", "< 5 сек", "для типовых вопросов"),
        ("Точность классификации", "94%", "ASR + n8n classifier"),
        ("Покрытие FAQ", "80%", "без перевода на оператора"),
        ("NPS пилота", "+12", "среди тестовой группы"),
    ]
    svg = [
        f'<svg class="ui-illustration" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" aria-label="Retail Group: пять ключевых метрик пилота Voice AI">',
        f'  <rect x="20" y="10" width="{w-40}" height="{h-20}" rx="8" class="ui-window" />',
        '  <text x="50" y="60" class="ui-main-title">Пилот Voice AI: ключевые метрики</text>',
        '  <text x="50" y="88" class="ui-subtitle">Результаты после 30 дней работы на линии ритейлера</text>',
    ]
    card_w, card_h, gap = 176, 180, 20
    start_x = (w - (card_w * 5 + gap * 4)) // 2
    y = 150
    for i, (label, value, sub) in enumerate(metrics):
        x = start_x + i * (card_w + gap)
        svg.append(f'  <rect x="{x}" y="{y}" width="{card_w}" height="{card_h}" rx="6" class="ui-source-card" />')
        svg.append(f'  <text x="{x + card_w/2}" y="{y + 35}" text-anchor="middle" class="ui-source-label">{escape_text(label.upper())}</text>')
        svg.append(f'  <text x="{x + card_w/2}" y="{y + 95}" text-anchor="middle" class="ui-main-title" style="font-size:32px;">{escape_text(value)}</text>')
        svg.append(f'  <text x="{x + card_w/2}" y="{y + 130}" text-anchor="middle" class="ui-subtitle">{escape_text(sub)}</text>')
    svg.append('</svg>')
    return "\n".join(svg)


def lora_scenario_svg(src_path: Path) -> str:
    """LoRA scenarios are already SVG files; read inline."""
    return src_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def escape_text(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def escape_attr(s: str) -> str:
    return escape_text(s).replace('"', "&quot;")


def cta_btn(cta, default_class="btn-ghost"):
    """Render a CTA button or disabled span."""
    if not cta or not cta.get("text"):
        return ""
    text = cta["text"]
    href = cta.get("href", "#")
    cls = "btn btn-primary" if cta.get("primary") else f"btn {default_class}"
    target = 'target="_blank" rel="noopener"' if cta.get("target_blank") else ""
    if cta.get("disabled") or not href or href == "#":
        return f'<span class="btn btn-ghost" style="opacity:0.55;cursor:default;">{escape_text(text)}</span>'
    return f'<a href="{escape_attr(href)}" class="{cls}" {target}>{escape_text(text)}</a>'


def render_template() -> jinja2.Template:
    env = jinja2.Environment(autoescape=False)
    return env.from_string(TEMPLATE)


# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------

TEMPLATE = r'''<!doctype html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="{{ meta_description }}">
  <meta property="og:title" content="{{ og_title }}">
  <meta property="og:description" content="{{ og_description }}">
  <meta property="og:type" content="website">
  <meta property="og:url" content="https://ai.alex-n8n.site/cases/{{ id }}.html">
  <meta property="og:image" content="{{ og_image }}">
  <meta property="og:locale" content="ru_RU">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{{ og_title }}">
  <meta name="twitter:description" content="{{ og_description }}">
  <meta name="twitter:image" content="{{ og_image }}">
  <link rel="canonical" href="https://ai.alex-n8n.site/cases/{{ id }}.html">
  <title>{{ title }}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,500;12..96,600;12..96,700&family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
  {% raw %}
  <script>
    (function() {
      const saved = localStorage.getItem('aip-theme-teal');
      if (saved === 'dark') document.documentElement.dataset.theme = 'dark';
      else if (saved === 'light') document.documentElement.dataset.theme = 'light';
    })();
  </script>
  <style>
    :root {
      --bg: #E3EAF2;
      --surface: #FFFFFF;
      --surface-elevated: #D8E0EA;
      --border: #C7D0DB;
      --text-primary: #1A1A1C;
      --text-secondary: #5A5A62;
      --text-muted: #7D7D85;
      --accent: #0D9488;
      --accent-hover: #0F766E;
      --accent-soft: rgba(13, 148, 136, 0.12);
      --focus: #14B8A6;
      --shadow-sm: 0 1px 2px rgba(13, 59, 55, 0.04);
      --shadow-md: 0 8px 24px rgba(13, 59, 55, 0.10);
      --shadow-lg: 0 18px 48px rgba(13, 59, 55, 0.14);
      --radius: 2px;
      --space-xs: 0.5rem;
      --space-sm: 0.75rem;
      --space-md: 1.25rem;
      --space-lg: 2rem;
      --space-xl: 3rem;
      --space-2xl: 5rem;
      --space-3xl: 7rem;
      --font-display: "Bricolage Grotesque", system-ui, sans-serif;
      --font-body: "Inter", system-ui, sans-serif;
      --font-mono: "IBM Plex Mono", ui-monospace, monospace;
    }

    @media (prefers-color-scheme: dark) {
      :root:not([data-theme="light"]) {
        --bg: #0a0a0f;
        --surface: #111118;
        --surface-elevated: #18181f;
        --border: rgba(255, 255, 255, 0.10);
        --text-primary: #f5f5f7;
        --text-secondary: #a1a1aa;
        --text-muted: #71717a;
        --accent: #14b8a6;
        --accent-hover: #2dd4bf;
        --accent-soft: rgba(20, 184, 166, 0.15);
        --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
        --shadow-md: 0 12px 32px rgba(0, 0, 0, 0.4);
        --shadow-lg: 0 24px 64px rgba(0, 0, 0, 0.55);
      }
    }

    :root[data-theme="dark"] {
      --bg: #0a0a0f;
      --surface: #111118;
      --surface-elevated: #18181f;
      --border: rgba(255, 255, 255, 0.10);
      --text-primary: #f5f5f7;
      --text-secondary: #a1a1aa;
      --text-muted: #71717a;
      --accent: #14b8a6;
      --accent-hover: #2dd4bf;
      --accent-soft: rgba(20, 184, 166, 0.15);
      --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
      --shadow-md: 0 12px 32px rgba(0, 0, 0, 0.4);
      --shadow-lg: 0 24px 64px rgba(0, 0, 0, 0.55);
    }

    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }

    body {
      margin: 0;
      font-family: var(--font-body);
      background: var(--bg);
      color: var(--text-primary);
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
    }

    a { color: var(--accent); text-decoration: none; }
    a:hover { color: var(--accent-hover); }
    a:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; border-radius: 2px; }

    .container {
      width: min(1140px, 92vw);
      margin-inline: auto;
    }

    .site-header {
      position: sticky;
      top: 0;
      z-index: 50;
      background: color-mix(in srgb, var(--bg) 92%, transparent);
      backdrop-filter: blur(8px);
      border-bottom: 1px solid var(--border);
    }

    .site-header__inner {
      display: flex;
      align-items: center;
      justify-content: space-between;
      height: 64px;
    }

    .logo {
      font-family: var(--font-display);
      font-weight: 600;
      font-size: 1.1rem;
      color: var(--text-primary);
      display: inline-flex;
      align-items: center;
      gap: var(--space-xs);
    }

    .logo__mark { color: var(--accent); font-size: 1.3rem; line-height: 1; }

    .nav {
      display: flex;
      gap: var(--space-md);
      font-size: 0.9rem;
      font-weight: 500;
    }

    .nav a { color: var(--text-secondary); }
    .nav a:hover { color: var(--text-primary); }

    .theme-toggle {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 2.2rem;
      height: 2.2rem;
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--text-secondary);
      border-radius: var(--radius);
      cursor: pointer;
      font-size: 1rem;
      transition: color 150ms ease, border-color 150ms ease, background 150ms ease;
    }

    .theme-toggle:hover { color: var(--text-primary); border-color: var(--text-muted); }
    .theme-toggle:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }

    .eyebrow {
      font-family: var(--font-mono);
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--accent);
      margin: 0 0 var(--space-md);
    }

    .section {
      padding: var(--space-3xl) 0;
      border-bottom: 1px solid var(--border);
    }

    .section:last-of-type { border-bottom: none; }

    .section__header {
      max-width: 720px;
      margin-bottom: var(--space-xl);
    }

    .section__title {
      font-family: var(--font-display);
      font-size: clamp(1.8rem, 3.2vw, 2.6rem);
      font-weight: 600;
      line-height: 1.15;
      margin: 0 0 var(--space-md);
    }

    .section__lead {
      color: var(--text-secondary);
      font-size: 1.05rem;
      margin: 0;
    }

    .btn {
      display: inline-flex;
      align-items: center;
      gap: var(--space-xs);
      padding: 0.7rem 1.2rem;
      border-radius: var(--radius);
      font-weight: 500;
      font-size: 0.9rem;
      transition: background 150ms ease, color 150ms ease, border-color 150ms ease;
      cursor: pointer;
      border: 1px solid transparent;
    }

    .btn:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }

    .btn-primary {
      background: var(--accent);
      color: #FFFFFF;
      border-color: var(--accent);
    }

    .btn-primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); color: #FFFFFF; }

    .btn-ghost {
      background: transparent;
      color: var(--text-secondary);
      border-color: var(--border);
    }

    .btn-ghost:hover { color: var(--text-primary); border-color: var(--text-muted); }

    .hero {
      padding: var(--space-xl) 0 var(--space-2xl);
      border-bottom: 1px solid var(--border);
    }

    .hero__inner {
      display: flex;
      flex-direction: column;
      gap: var(--space-lg);
    }

    .hero__body {
      text-align: center;
      max-width: 640px;
      margin-inline: auto;
    }

    .hero__eyebrow { margin-bottom: var(--space-sm); }

    .hero__title {
      font-family: var(--font-display);
      font-size: clamp(1.9rem, 3.8vw, 2.8rem);
      line-height: 1.08;
      font-weight: 600;
      margin: 0 0 var(--space-sm);
    }

    .hero__lead {
      font-size: clamp(1rem, 1.3vw, 1.1rem);
      color: var(--text-secondary);
      margin: 0 0 var(--space-md);
      max-width: 600px;
      margin-inline: auto;
    }

    .hero__actions { display: flex; gap: var(--space-sm); flex-wrap: wrap; justify-content: center; margin-bottom: 0; }

    .hero__media {
      position: relative;
      background: var(--surface-elevated);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: var(--space-md);
      box-shadow: var(--shadow-lg);
      overflow: hidden;
      max-width: 900px;
      margin-inline: auto;
      width: 100%;
    }

    .hero__media::after {
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(135deg, color-mix(in srgb, var(--accent) 10%, transparent) 0%, transparent 55%);
      pointer-events: none;
    }

    .hero__screenshot {
      position: relative;
      z-index: 1;
      width: 100%;
      aspect-ratio: 16/9;
      object-fit: cover;
      object-position: top left;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      display: block;
    }

    .preview-dark { display: block; }
    .preview-light { display: none; }

    @media (prefers-color-scheme: dark) {
      :root:not([data-theme="light"]) .preview-dark { display: none; }
      :root:not([data-theme="light"]) .preview-light { display: block; }
    }

    :root[data-theme="dark"] .preview-dark { display: none; }
    :root[data-theme="dark"] .preview-light { display: block; }

    .summary {
      padding: 0 0 var(--space-3xl);
      border-bottom: 1px solid var(--border);
    }

    .summary__grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: var(--space-md);
    }

    .summary__item {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: var(--space-md);
      box-shadow: var(--shadow-sm);
    }

    .summary__label {
      font-family: var(--font-mono);
      font-size: 0.65rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--text-muted);
      margin-bottom: var(--space-xs);
    }

    .summary__value {
      font-size: 0.95rem;
      color: var(--text-primary);
      line-height: 1.4;
    }

    .summary__value a { font-size: 0.9rem; }

    .ba-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: var(--space-lg);
      margin-bottom: var(--space-xl);
    }

    .ba-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: var(--space-lg);
      box-shadow: var(--shadow-sm);
    }

    .ba-card--accent {
      border-color: color-mix(in srgb, var(--accent) 45%, var(--border));
      background: linear-gradient(135deg, var(--surface) 0%, color-mix(in srgb, var(--accent-soft) 40%, var(--surface)) 100%);
    }

    .ba-card__title {
      font-family: var(--font-display);
      font-size: 1.15rem;
      font-weight: 600;
      margin: 0 0 var(--space-md);
      display: flex;
      align-items: center;
      gap: var(--space-sm);
    }

    .ba-card__list {
      margin: 0;
      padding-left: var(--space-md);
      color: var(--text-secondary);
      font-size: 0.95rem;
    }

    .ba-card__list li { margin-bottom: var(--space-sm); }

    .ba-arrow {
      display: none;
      align-items: center;
      justify-content: center;
      color: var(--accent);
      font-size: 1.5rem;
    }

    .problem-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: var(--space-lg);
      box-shadow: var(--shadow-sm);
    }

    .problem-card__title {
      font-family: var(--font-display);
      font-size: 1.1rem;
      font-weight: 600;
      margin: 0 0 var(--space-sm);
    }

    .problem-card__text {
      font-size: 0.95rem;
      color: var(--text-secondary);
      margin: 0;
    }

    .solution-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: var(--space-lg);
    }

    .solution-card {
      display: flex;
      gap: var(--space-md);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: var(--space-lg);
      box-shadow: var(--shadow-sm);
    }

    .solution-card__icon {
      width: 44px;
      height: 44px;
      min-width: 44px;
      border-radius: var(--radius);
      background: var(--accent-soft);
      color: var(--accent);
      display: grid;
      place-items: center;
      font-size: 1.2rem;
    }

    .solution-card__title {
      font-family: var(--font-display);
      font-size: 1.1rem;
      font-weight: 600;
      margin: 0 0 var(--space-xs);
    }

    .solution-card__text {
      font-size: 0.95rem;
      color: var(--text-secondary);
      margin: 0;
    }

    .pipeline-diagram {
      width: 100%;
      height: auto;
      max-width: 100%;
    }

    .pipeline-diagram text {
      font-family: var(--font-body);
      fill: var(--text-primary);
    }

    .pipeline-diagram .node-rect {
      fill: var(--surface);
      stroke: var(--border);
      stroke-width: 1.5;
    }

    .pipeline-diagram .node-accent {
      fill: var(--accent-soft);
      stroke: var(--accent);
      stroke-width: 1.5;
    }

    .pipeline-diagram .arrow {
      fill: none;
      stroke: var(--accent);
      stroke-width: 2;
      stroke-linecap: round;
      stroke-linejoin: round;
    }

    .pipeline-diagram .arrow-head {
      fill: var(--accent);
    }

    .pipeline-diagram .title-text {
      font-family: var(--font-display);
      font-size: 15px;
      font-weight: 600;
    }

    .pipeline-diagram .title-text--large {
      font-size: 17px;
    }

    .pipeline-diagram .body-text {
      font-size: 13px;
      fill: var(--text-secondary);
    }

    .pipeline-diagram .body-text--large {
      font-size: 15px;
    }

    .pipeline-cards {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: var(--space-lg);
      margin-top: var(--space-xl);
    }

    .pipeline-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: var(--space-md);
      box-shadow: var(--shadow-sm);
    }

    .pipeline-card__number {
      font-family: var(--font-mono);
      font-size: 0.7rem;
      color: var(--accent);
      margin-bottom: var(--space-xs);
    }

    .pipeline-card__title {
      font-family: var(--font-display);
      font-size: 1rem;
      font-weight: 600;
      margin: 0 0 var(--space-xs);
    }

    .pipeline-card__text {
      font-size: 0.88rem;
      color: var(--text-secondary);
      margin: 0;
    }

    .demo-block {
      margin-bottom: var(--space-2xl);
    }

    .demo-block:last-child {
      margin-bottom: 0;
    }

    .demo-block__header {
      margin-bottom: var(--space-md);
      max-width: 720px;
    }

    .demo-block__label {
      font-family: var(--font-mono);
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--accent);
      margin-bottom: var(--space-sm);
    }

    .demo-block__title {
      font-family: var(--font-display);
      font-size: 1.4rem;
      font-weight: 600;
      margin: 0 0 var(--space-xs);
    }

    .demo-block__text {
      color: var(--text-secondary);
      margin: 0;
      font-size: 0.95rem;
    }

    .demo-frame {
      position: relative;
      background: var(--surface-elevated);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: var(--space-md);
      box-shadow: var(--shadow-md);
      cursor: zoom-in;
      transition: box-shadow 180ms ease, border-color 180ms ease;
      overflow: hidden;
    }

    .demo-frame:hover {
      border-color: color-mix(in srgb, var(--accent) 45%, var(--border));
      box-shadow: var(--shadow-lg);
    }

    .demo-frame img {
      width: 100%;
      height: auto;
      max-height: 560px;
      object-fit: contain;
      object-position: top left;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      display: block;
    }

    .demo-frame__hint {
      position: absolute;
      bottom: var(--space-md);
      right: var(--space-md);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 0.35rem 0.6rem;
      font-family: var(--font-mono);
      font-size: 0.7rem;
      color: var(--text-muted);
      opacity: 0;
      transform: translateY(4px);
      transition: opacity 180ms ease, transform 180ms ease;
    }

    .demo-frame:hover .demo-frame__hint {
      opacity: 1;
      transform: translateY(0);
    }

    .ui-illustration {
      width: 100%;
      height: auto;
      max-width: 100%;
      display: block;
    }

    .ui-illustration text {
      font-family: var(--font-body);
    }

    .ui-illustration .ui-window {
      fill: var(--surface);
      stroke: var(--border);
      stroke-width: 1.5;
    }

    .ui-illustration .ui-header {
      fill: var(--surface-elevated);
      stroke: var(--border);
      stroke-width: 1.5;
    }

    .ui-illustration .ui-title {
      font-size: 15px;
      font-weight: 600;
      fill: var(--text-primary);
    }

    .ui-illustration .ui-subtitle {
      font-size: 11px;
      fill: var(--text-muted);
    }

    .ui-illustration .ui-avatar {
      fill: var(--accent);
    }

    .ui-illustration .ui-sidebar {
      fill: var(--surface-elevated);
      stroke: var(--border);
      stroke-width: 1.5;
    }

    .ui-illustration .ui-sidebar-title {
      font-family: var(--font-display);
      font-size: 16px;
      font-weight: 600;
      fill: var(--text-primary);
    }

    .ui-illustration .ui-sidebar-item {
      fill: transparent;
    }

    .ui-illustration .ui-sidebar-item-active {
      fill: var(--accent-soft);
      stroke: var(--accent);
      stroke-width: 1;
    }

    .ui-illustration .ui-sidebar-text {
      font-size: 13px;
      fill: var(--text-secondary);
    }

    .ui-illustration .ui-sidebar-text-active {
      font-size: 13px;
      font-weight: 500;
      fill: var(--accent);
    }

    .ui-illustration .ui-main-title {
      font-family: var(--font-display);
      font-size: 18px;
      font-weight: 600;
      fill: var(--text-primary);
    }

    .ui-illustration .ui-msg-user {
      fill: var(--accent);
    }

    .ui-illustration .ui-msg-bot {
      fill: var(--surface-elevated);
      stroke: var(--border);
      stroke-width: 1;
    }

    .ui-illustration .ui-msg-text-user {
      font-size: 14px;
      fill: #ffffff;
    }

    .ui-illustration .ui-msg-text-bot {
      font-size: 14px;
      fill: var(--text-primary);
    }

    .ui-illustration .ui-source-card {
      fill: var(--surface);
      stroke: var(--accent);
      stroke-width: 1.5;
    }

    .ui-illustration .ui-source-label {
      font-family: var(--font-mono);
      font-size: 10px;
      font-weight: 500;
      fill: var(--accent);
    }

    .ui-illustration .ui-input {
      fill: var(--surface-elevated);
      stroke: var(--border);
      stroke-width: 1;
    }

    .ui-illustration .ui-input-text {
      font-size: 13px;
      fill: var(--text-muted);
    }

    .ui-illustration .ui-btn-primary {
      fill: var(--accent);
    }

    .ui-illustration .ui-btn-text {
      font-size: 12px;
      font-weight: 500;
      fill: #ffffff;
    }

    .ui-illustration .ui-status-published {
      fill: rgba(34, 197, 94, 0.15);
      stroke: #22c55e;
      stroke-width: 1;
    }

    .ui-illustration .ui-status-text {
      font-size: 12px;
      font-weight: 500;
      fill: #22c55e;
    }

    .ui-illustration .ui-toggle {
      fill: var(--surface-elevated);
      stroke: var(--border);
      stroke-width: 1;
    }

    .ui-illustration .ui-toggle-active {
      fill: var(--accent-soft);
      stroke: var(--accent);
      stroke-width: 1.5;
    }

    .ui-illustration .ui-toggle-text {
      font-size: 11px;
      font-weight: 500;
      fill: var(--accent);
    }

    .ui-illustration .ui-toggle-text-inactive {
      font-size: 11px;
      fill: var(--text-muted);
    }

    .ui-illustration .ui-source-stripe {
      fill: var(--accent);
    }

    .ui-illustration .ui-source-title {
      font-size: 13px;
      font-weight: 600;
      fill: var(--text-primary);
    }

    .ui-illustration .ui-send {
      fill: var(--accent);
    }

    .ui-illustration .ui-send-arrow {
      stroke: #ffffff;
      stroke-width: 2;
      fill: none;
      stroke-linecap: round;
      stroke-linejoin: round;
    }

    .ui-illustration .ui-msg-text-bot-muted {
      font-size: 12px;
      fill: var(--text-secondary);
    }

    .ui-illustration .ui-table-header-text {
      font-size: 11px;
      font-weight: 600;
      fill: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }

    .quote {
      background: var(--surface);
      border: 1px solid var(--border);
      border-left: 4px solid var(--accent);
      border-radius: var(--radius);
      padding: var(--space-xl);
      box-shadow: var(--shadow-sm);
    }

    .quote__text {
      font-family: var(--font-display);
      font-size: 1.35rem;
      line-height: 1.35;
      margin: 0 0 var(--space-md);
      color: var(--text-primary);
    }

    .quote__author {
      font-size: 0.95rem;
      color: var(--text-secondary);
    }

    .quote__author strong { color: var(--text-primary); }

    .final {
      background: var(--surface);
      border-top: 1px solid var(--border);
      border-bottom: 1px solid var(--border);
    }

    .final__inner {
      display: grid;
      grid-template-columns: 1.2fr 1fr;
      gap: var(--space-xl);
      align-items: center;
    }

    .final__title {
      font-family: var(--font-display);
      font-size: clamp(1.8rem, 3.2vw, 2.6rem);
      font-weight: 600;
      margin: 0 0 var(--space-md);
      line-height: 1.15;
    }

    .final__lead {
      color: var(--text-secondary);
      margin: 0 0 var(--space-lg);
      max-width: 520px;
    }

    .final__actions { display: flex; gap: var(--space-sm); flex-wrap: wrap; margin-bottom: var(--space-lg); }

    .final__links {
      display: flex;
      flex-direction: column;
      gap: var(--space-sm);
      font-size: 0.92rem;
      color: var(--text-secondary);
    }

    .final__links a { display: inline-flex; align-items: center; gap: 0.4rem; }

    .site-footer {
      border-top: 1px solid var(--border);
      padding: var(--space-lg) 0;
    }

    .site-footer__inner {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.85rem;
      color: var(--text-muted);
      flex-wrap: wrap;
      gap: var(--space-sm);
    }

    .chat-launcher {
      position: fixed;
      bottom: 24px;
      right: 24px;
      width: 56px;
      height: 56px;
      border-radius: 999px;
      background: var(--accent);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: var(--shadow-md);
      cursor: pointer;
      border: none;
      outline: none;
      transition: transform 150ms ease, box-shadow 150ms ease;
      z-index: 1000;
      color: #fff;
      font-size: 1.4rem;
    }

    .chat-launcher:hover { transform: translateY(-2px); box-shadow: var(--shadow-lg); }
    .chat-widget {
      position: fixed;
      bottom: 92px;
      right: 24px;
      width: 380px;
      max-width: calc(100vw - 32px);
      height: 560px;
      max-height: calc(100vh - 120px);
      background: var(--surface);
      border-radius: var(--radius);
      box-shadow: var(--shadow-lg);
      display: none;
      flex-direction: column;
      overflow: hidden;
      border: 1px solid var(--border);
      z-index: 1001;
    }

    .chat-header {
      padding: var(--space-md) var(--space-lg);
      background: var(--surface-elevated);
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      color: var(--text-primary);
    }

    .chat-header-left { display: flex; gap: var(--space-sm); align-items: center; }
    .chat-avatar {
      width: 36px;
      height: 36px;
      border-radius: 999px;
      background: var(--accent);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 14px;
      font-weight: 700;
      color: #fff;
    }

    .chat-title { font-size: 0.9375rem; font-weight: 600; }
    .chat-subtitle { font-size: 0.75rem; color: var(--text-muted); }
    .chat-close {
      border: none;
      background: transparent;
      color: var(--text-secondary);
      font-size: 20px;
      cursor: pointer;
      opacity: 0.8;
      transition: opacity 150ms ease;
      padding: var(--space-xs);
    }

    .chat-close:hover { opacity: 1; }
    .chat-messages {
      flex: 1;
      padding: var(--space-md);
      display: flex;
      flex-direction: column;
      gap: var(--space-sm);
      overflow-y: auto;
      background: var(--bg);
    }

    .chat-message {
      max-width: 85%;
      border-radius: var(--radius);
      padding: var(--space-sm) var(--space-md);
      font-size: 0.875rem;
      line-height: 1.5;
      word-wrap: break-word;
      white-space: pre-wrap;
    }

    .chat-message.user {
      margin-left: auto;
      background: var(--accent);
      color: #fff;
    }

    .chat-message.bot {
      margin-right: auto;
      background: var(--surface-elevated);
      border: 1px solid var(--border);
      color: var(--text-primary);
    }

    .chat-message--error {
      background: rgba(239, 68, 68, 0.12);
      border-color: #ef4444;
      color: var(--text-primary);
    }

    .chat-message__text { margin-bottom: 0; }
    .chat-message__meta {
      margin-top: var(--space-sm);
      padding-top: var(--space-sm);
      border-top: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      gap: var(--space-xs);
    }

    .chat-message__meta-label { font-size: 0.6875rem; color: var(--text-muted); margin-right: var(--space-xs); }
    .chat-message__meta-value { font-size: 0.75rem; color: var(--text-secondary); }
    .chat-message__sources,
    .chat-message__provider,
    .chat-message__time { display: flex; flex-wrap: wrap; gap: var(--space-xs); }
    .chat-message__cache {
      display: inline-block;
      font-size: 0.625rem;
      padding: 2px var(--space-sm);
      background: rgba(34, 197, 94, 0.12);
      color: #22c55e;
      border-radius: var(--radius);
      border: 1px solid #22c55e;
    }

    .typing-indicator { display: inline-flex; gap: 3px; padding: var(--space-xs) 0; }
    .typing-indicator .dot {
      width: 6px;
      height: 6px;
      border-radius: 999px;
      background: var(--text-muted);
      animation: typing 1s infinite ease-in-out;
    }

    .typing-indicator .dot:nth-child(2) { animation-delay: 0.2s; }
    .typing-indicator .dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes typing {
      0%, 80%, 100% { opacity: 0.3; transform: translateY(0); }
      40% { opacity: 1; transform: translateY(-2px); }
    }

    .chat-footer {
      padding: var(--space-sm) var(--space-md);
      border-top: 1px solid var(--border);
      background: var(--surface);
      display: flex;
      gap: var(--space-sm);
      align-items: center;
    }

    .chat-input {
      flex: 1;
      border-radius: 999px;
      border: 1px solid var(--border);
      padding: var(--space-sm) var(--space-md);
      background: var(--bg);
      color: var(--text-primary);
      font-size: 0.875rem;
      outline: none;
      transition: border-color 150ms ease;
    }

    .chat-input:focus { border-color: var(--accent); }
    .chat-input::placeholder { color: var(--text-muted); }
    .chat-send {
      border-radius: 999px;
      border: none;
      padding: var(--space-sm) var(--space-md);
      background: var(--accent);
      color: #fff;
      font-size: 0.875rem;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: var(--space-xs);
      transition: opacity 150ms ease;
    }

    .chat-send:hover:not(:disabled) { opacity: 0.9; }
    .chat-send:disabled { opacity: 0.5; cursor: default; }
    .chat-send span { font-size: 1rem; }

    @media (max-width: 900px) {
      .final__inner { grid-template-columns: 1fr; }
      .summary__grid,
      .solution-grid,
      .ba-grid { grid-template-columns: 1fr; }
      .ba-arrow { display: none; }
      .pipeline-cards { grid-template-columns: 1fr; }
      .section { padding: var(--space-2xl) 0; }
      .chat-widget { right: 16px; bottom: 84px; }
      .chat-launcher { right: 16px; bottom: 16px; }
    }
  </style>
  {% endraw %}
</head>
<body>
  <header class="site-header">
    <div class="container site-header__inner">
      <a href="/" class="logo"><span class="logo__mark">◇</span> AI Portfolio</a>
      <nav class="nav" aria-label="Primary">
        <a href="/">Главная</a>
        <a href="/portfolio.html">Проекты</a>
        <a href="/services.html">Услуги</a>
        <a href="/contacts.html">Контакты</a>
      </nav>
      <button class="theme-toggle" id="theme-toggle" aria-label="Toggle theme">🌙</button>
    </div>
  </header>

  <main>
    <!-- 1. Hero -->
    <section class="hero">
      <div class="container hero__inner">
        <div class="hero__body">
          <p class="eyebrow hero__eyebrow">{{ eyebrow }}</p>
          <h1 class="hero__title">{{ hero_title }}</h1>
          <p class="hero__lead">{{ hero_lead }}</p>
          <div class="hero__actions">
            {{ cta_btn(hero_cta_primary, 'btn-primary') }}
            {{ cta_btn(hero_cta_secondary) }}
            {{ cta_btn(hero_cta_tertiary) }}
            {% if hero_cta_quaternary %}{{ cta_btn(hero_cta_quaternary) }}{% endif %}
          </div>
        </div>
        <div class="hero__media">
          <img class="hero__screenshot preview-dark" src="{{ hero_screenshot_dark }}" alt="{{ hero_screenshot_alt_dark }}" loading="eager">
          <img class="hero__screenshot preview-light" src="{{ hero_screenshot_light }}" alt="{{ hero_screenshot_alt_light }}" loading="eager">
        </div>
      </div>
    </section>

    <!-- 2. Case summary -->
    <section class="summary">
      <div class="container">
        <div class="summary__grid">
          {% for item in summary_items %}
          <div class="summary__item">
            <div class="summary__label">{{ item.label }}</div>
            <div class="summary__value">{% if item.value_html %}{{ item.value_html }}{% else %}{{ item.value }}{% endif %}</div>
          </div>
          {% endfor %}
        </div>
      </div>
    </section>

    <!-- 3. Before / After -->
    <section class="section" id="results">
      <div class="container">
        <div class="section__header">
          <p class="eyebrow">Результат</p>
          <h2 class="section__title">{{ results_title }}</h2>
          <p class="section__lead">{{ results_lead }}</p>
        </div>

        <div class="ba-grid">
          <div class="ba-card">
            <h3 class="ba-card__title"><span>❌</span> До</h3>
            <ul class="ba-card__list">
              {% for b in before %}
              <li>{{ b }}</li>
              {% endfor %}
            </ul>
          </div>
          <div class="ba-arrow">→</div>
          <div class="ba-card ba-card--accent">
            <h3 class="ba-card__title"><span>✅</span> После</h3>
            <ul class="ba-card__list">
              {% for a in after %}
              <li>{{ a }}</li>
              {% endfor %}
            </ul>
          </div>
        </div>

        {% if metrics %}
        <div class="summary__grid" style="grid-template-columns: repeat({{ metrics|length }}, 1fr);">
          {% for m in metrics %}
          <div class="summary__item">
            <div class="summary__label">{{ m.label }}</div>
            <div class="summary__value"><strong>{{ m.value }}</strong>{% if m.suffix %} {{ m.suffix }}{% endif %}</div>
          </div>
          {% endfor %}
        </div>
        {% endif %}
      </div>
    </section>

    <!-- 4. Problem -->
    <section class="section" id="problem">
      <div class="container">
        <div class="section__header">
          <p class="eyebrow">Проблема</p>
          <h2 class="section__title">{{ problem_title }}</h2>
          <p class="section__lead">{{ problem_lead }}</p>
        </div>

        <div class="ba-grid" style="grid-template-columns: repeat({{ problem_cards|length }}, 1fr);">
          {% for card in problem_cards %}
          <div class="problem-card">
            <h3 class="problem-card__title">{{ card.title }}</h3>
            <p class="problem-card__text">{{ card.text }}</p>
          </div>
          {% endfor %}
        </div>
      </div>
    </section>

    <!-- 5. Solution -->
    <section class="section" id="solution">
      <div class="container">
        <div class="section__header">
          <p class="eyebrow">Решение</p>
          <h2 class="section__title">{{ solution_title }}</h2>
          <p class="section__lead">{{ solution_lead }}</p>
        </div>

        <div class="solution-grid">
          {% for card in solution_cards %}
          <div class="solution-card">
            <div class="solution-card__icon">{{ card.icon }}</div>
            <div>
              <h3 class="solution-card__title">{{ card.title }}</h3>
              <p class="solution-card__text">{{ card.text }}</p>
            </div>
          </div>
          {% endfor %}
        </div>
      </div>
    </section>

    <!-- 6. How it works -->
    <section class="section" id="how-it-works">
      <div class="container">
        <div class="section__header">
          <p class="eyebrow">Как это работает</p>
          <h2 class="section__title">{{ pipeline_title }}</h2>
          <p class="section__lead">{{ pipeline_lead }}</p>
        </div>

        {{ pipeline_svg_html }}

        <div class="pipeline-cards">
          {% for step in pipeline_steps %}
          <div class="pipeline-card">
            <div class="pipeline-card__number">{{ step.number }}</div>
            <h3 class="pipeline-card__title">{{ step.title }}</h3>
            <p class="pipeline-card__text">{{ step.text }}</p>
          </div>
          {% endfor %}
        </div>
      </div>
    </section>

    <!-- 7. UX -->
    <section class="section" id="ux">
      <div class="container">
        <div class="section__header">
          <p class="eyebrow">{{ ux_title }}</p>
          <h2 class="section__title">{{ ux_main_title }}</h2>
          <p class="section__lead">{{ ux_lead }}</p>
        </div>

        {% for scenario in scenarios %}
        <div class="demo-block">
          <div class="demo-block__header">
            <div class="demo-block__label">{{ scenario.label }}</div>
            <h3 class="demo-block__title">{{ scenario.title }}</h3>
            <p class="demo-block__text">{{ scenario.text }}</p>
          </div>
          {% if scenario.type == 'image' %}
          <div class="demo-frame">
            <img src="{{ scenario.src }}" alt="{{ scenario.alt }}">
            <div class="demo-frame__hint">Кликните для полного размера</div>
          </div>
          {% else %}
          {{ scenario.svg_html }}
          {% endif %}
        </div>
        {% endfor %}
      </div>
    </section>

    <!-- 8. Quote -->
    <section class="section">
      <div class="container">
        <div class="quote">
          <p class="quote__text">{{ quote }}</p>
        </div>
      </div>
    </section>

    <!-- 9. Final CTA -->
    <section class="section final">
      <div class="container final__inner">
        <div>
          <p class="eyebrow">Следующий шаг</p>
          <h2 class="final__title">{{ final_title }}</h2>
          <p class="final__lead">{{ final_lead }}</p>
          <div class="final__actions">
            {{ cta_btn(final_cta_primary, 'btn-primary') }}
            {{ cta_btn(final_cta_secondary) }}
            {{ cta_btn(final_cta_tertiary) }}
            {% if final_cta_quaternary %}{{ cta_btn(final_cta_quaternary) }}{% endif %}
          </div>
        </div>
        <div class="final__links">
          <span><strong>Александр Гуляаев</strong>, AI Automation Portfolio Lab</span>
          <a href="https://t.me/AlexLvGulyaev" target="_blank" rel="noopener">Telegram: @AlexLvGulyaev</a>
          <a href="mailto:sbs.gulyaev.al@gmail.com">sbs.gulyaev.al@gmail.com</a>
          {% for link in final_links %}
          <a href="{{ link.href }}" {% if link.target_blank %}target="_blank" rel="noopener"{% endif %}>{{ link.text }}</a>
          {% endfor %}
        </div>
      </div>
    </section>
  </main>

  <footer class="site-footer">
    <div class="container site-footer__inner">
      <span>© 2026 AI Automation Portfolio Lab</span>
      <span>{{ footer_positioning }}</span>
    </div>
  </footer>

  <button class="chat-launcher" id="chat-launcher" aria-label="Открыть AI-ассистента">
    <span>💬</span>
  </button>

  <div class="chat-widget" id="chat-widget">
    <div class="chat-header">
      <div class="chat-header-left">
        <div class="chat-avatar">AI</div>
        <div>
          <div class="chat-title">AI-ассистент</div>
          <div class="chat-subtitle">Спросите о кейсах и услугах</div>
        </div>
      </div>
      <button class="chat-close" id="chat-close" aria-label="Закрыть чат">×</button>
    </div>
    <div class="chat-messages" id="chat-messages"></div>
    <div class="chat-footer">
      <input id="chat-input" class="chat-input" placeholder="Напишите вопрос..." type="text">
      <button id="chat-send" class="chat-send"><span>➤</span></button>
    </div>
  </div>

  <script src="../js/api-client.js"></script>
  <script src="../js/chat-widget.js"></script>
  {% raw %}
  <script>
    (function() {
      const btn = document.getElementById('theme-toggle');
      const root = document.documentElement;

      function isDark() {
        return root.dataset.theme === 'dark' || (!root.dataset.theme && window.matchMedia('(prefers-color-scheme: dark)').matches);
      }

      function updateIcon() {
        btn.textContent = isDark() ? '☀️' : '🌙';
        btn.setAttribute('aria-label', isDark() ? 'Переключить на светлую тему' : 'Переключить на тёмную тему');
      }

      btn.addEventListener('click', function() {
        if (isDark()) {
          root.dataset.theme = 'light';
          localStorage.setItem('aip-theme-teal', 'light');
        } else {
          root.dataset.theme = 'dark';
          localStorage.setItem('aip-theme-teal', 'dark');
        }
        updateIcon();
      });

      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function() {
        if (!localStorage.getItem('aip-theme-teal')) updateIcon();
      });

      updateIcon();
    })();
  </script>
  {% endraw %}
</body>
</html>
'''


def build_project(project: dict) -> dict:
    """Prepare render context: copy assets, generate SVGs, derive derived fields."""
    pid = project["id"]
    case_dir = ASSETS_DIR / pid
    case_dir.mkdir(parents=True, exist_ok=True)

    # Hero screenshots
    hero_dark = project.get("hero_screenshot_dark", "")
    hero_light = project.get("hero_screenshot_light", "")
    hero_dark_site = ""
    hero_light_site = ""
    if hero_dark:
        src = rel_to_root(hero_dark)
        if src.exists():
            hero_dark_site = f"{SCREENSHOT_PREFIX}/{src.name}"
            if not (SCREENSHOTS_DIR / src.name).exists():
                shutil.copyfile(src, SCREENSHOTS_DIR / src.name)
    if hero_light:
        src = rel_to_root(hero_light)
        if src.exists():
            hero_light_site = f"{SCREENSHOT_PREFIX}/{src.name}"
            if not (SCREENSHOTS_DIR / src.name).exists():
                shutil.copyfile(src, SCREENSHOTS_DIR / src.name)

    # Fallback: if no screenshots discovered, use site paths from registry
    if not hero_dark_site:
        hero_dark_site = project.get("hero_screenshot_dark_site", "")
    if not hero_light_site:
        hero_light_site = project.get("hero_screenshot_light_site", "")

    # Pipeline SVG
    pipeline_nodes = project.get("pipeline_svg_nodes", [])
    pipeline_svg_html = pipeline_svg(
        pipeline_nodes,
        f"Схема работы {project['name']}: от входа к результату",
    )

    # Scenarios
    scenarios = []
    for i, key in enumerate(["scenario_1", "scenario_2"], start=1):
        sc = project.get(key)
        if not sc:
            continue
        entry = {
            "label": sc.get("label", f"Сценарий {i}"),
            "title": sc.get("title", ""),
            "text": sc.get("text", ""),
            "alt": sc.get("alt", ""),
        }
        stype = sc.get("type", "image")
        src = sc.get("src", "")
        if stype == "image":
            src_path = rel_to_root(src)
            if src_path.exists():
                entry["type"] = "image"
                entry["src"] = copy_to_assets(src_path, case_dir, f"scenario-{i}")
            else:
                entry["type"] = "image"
                entry["src"] = src  # keep as-is, may be broken
        elif stype == "svg":
            src_path = rel_to_root(src)
            if src_path.exists():
                entry["type"] = "svg"
                entry["svg_html"] = lora_scenario_svg(src_path)
            else:
                entry["type"] = "image"
                entry["src"] = src
        elif stype == "stylized":
            entry["type"] = "svg"
            if pid == "hr-assistant":
                entry["svg_html"] = hr_scenario_1_svg() if i == 1 else hr_scenario_2_svg()
            elif pid == "ai-data-assistant":
                entry["svg_html"] = ada_scenario_1_svg() if i == 1 else ada_scenario_2_svg()
            elif pid == "review-flow":
                entry["svg_html"] = rf_scenario_1_svg() if i == 1 else rf_scenario_2_svg()
            elif pid == "review-auto-responder":
                entry["svg_html"] = rar_scenario_1_svg() if i == 1 else rar_scenario_2_svg()
            elif pid == "retail-group" and i == 2:
                entry["svg_html"] = retail_metrics_svg()
            else:
                entry["svg_html"] = pipeline_svg([], "")
        else:
            entry["type"] = "image"
            entry["src"] = src
        scenarios.append(entry)

    # Derived text fields
    context = {
        "id": pid,
        "title": project.get("title") or f"{project['name']} — AI Portfolio",
        "meta_description": project.get("hero_lead", ""),
        "og_title": project.get("og_title") or f"{project['name']} — {project.get('domain','')}",
        "og_description": project.get("hero_lead", ""),
        "og_image": hero_light_site or hero_dark_site or "",
        "eyebrow": project.get("eyebrow", ""),
        "hero_title": project.get("hero_title", ""),
        "hero_lead": project.get("hero_lead", ""),
        "hero_cta_primary": project.get("hero_cta_primary"),
        "hero_cta_secondary": project.get("hero_cta_secondary"),
        "hero_cta_tertiary": project.get("hero_cta_tertiary"),
        "hero_cta_quaternary": project.get("hero_cta_quaternary"),
        "hero_screenshot_dark": hero_dark_site,
        "hero_screenshot_light": hero_light_site,
        "hero_screenshot_alt_dark": project.get("hero_screenshot_alt_dark") or project.get("hero_screenshot_alt", ""),
        "hero_screenshot_alt_light": project.get("hero_screenshot_alt_light") or project.get("hero_screenshot_alt", ""),
        "summary_items": project.get("summary_items", []),
        "results_title": project.get("results_title", "Что меняется для команды"),
        "results_lead": project.get("results_lead", ""),
        "before": project.get("before", []),
        "after": project.get("after", []),
        "metrics": project.get("metrics", []),
        "problem_title": project.get("problem_title", ""),
        "problem_lead": project.get("problem_lead", ""),
        "problem_cards": project.get("problem_cards", []),
        "solution_title": project.get("solution_title", ""),
        "solution_lead": project.get("solution_lead", ""),
        "solution_cards": project.get("solution_cards", []),
        "pipeline_title": project.get("pipeline_title", ""),
        "pipeline_lead": project.get("pipeline_lead", ""),
        "pipeline_svg_html": pipeline_svg_html,
        "pipeline_steps": project.get("pipeline_steps", []),
        "ux_title": project.get("ux_title", "Интерфейсы"),
        "ux_main_title": project.get("ux_main_title", "Как это выглядит внутри"),
        "ux_lead": project.get("ux_lead", ""),
        "scenarios": scenarios,
        "quote": project.get("quote", ""),
        "final_title": project.get("final_title", ""),
        "final_lead": project.get("final_lead", ""),
        "final_cta_primary": project.get("final_cta_primary"),
        "final_cta_secondary": project.get("final_cta_secondary"),
        "final_cta_tertiary": project.get("final_cta_tertiary"),
        "final_cta_quaternary": project.get("final_cta_quaternary"),
        "final_links": project.get("final_links", []),
        "footer_positioning": project.get("footer_positioning") or f"{project['name']} — {project.get('domain','')}",
    }
    return context


def render_project(project: dict, template: jinja2.Template):
    context = build_project(project)
    html = template.render(**context, cta_btn=cta_btn)
    out = CASES_DIR / f"{project['id']}.html"
    out.write_text(html, encoding="utf-8")
    return out


def main():
    ensure_dirs()
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    template = render_template()
    generated = []
    skipped = []
    for project in data.get("projects", []):
        pid = project.get("id")
        if pid in MANUAL_CASES:
            skipped.append(pid)
            continue
        out = render_project(project, template)
        generated.append(str(out))
    print("Generated files:")
    for g in generated:
        print(g)
    if skipped:
        print("Skipped manual cases:")
        for s in skipped:
            print(f"  - {s}")


if __name__ == "__main__":
    main()
