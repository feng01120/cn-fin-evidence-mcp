# -*- coding: utf-8 -*-
"""把 `fin-evidence demo` 的输出渲染成 README 用的终端截图与 GIF。

用法：
    PYTHONPATH=src python scripts/render_demo.py
输出：
    docs/demo.png
    docs/demo.gif
"""
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs'
FONT_PATH = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
MONO_PATH = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'

WIDTH, HEIGHT = 1180, 820
PAD_X, PAD_TOP, LINE_H = 34, 74, 29
BG = '#0d1117'
BAR = '#161b22'
TEXT = '#c9d1d9'
DIM = '#8b949e'
CYAN = '#79c0ff'
GREEN = '#7ee787'
YELLOW = '#e3b341'
RED = '#ff7b72'


def load_font(size=19):
    for path in (MONO_PATH, FONT_PATH):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def color_for(line):
    if line.startswith('[1]') or line.startswith('[2]') or line.startswith('[3]') or line.startswith('[4]'):
        return CYAN
    if 'pass_with_restatement' in line or 'restatement_match' in line:
        return GREEN
    if 'fail' in line and 'verdict' in line:
        return RED
    if line.startswith('cn-fin-evidence'):
        return YELLOW
    if line.startswith('    status') or line.startswith('    verdict'):
        return YELLOW
    if line.startswith('    "') or line.startswith('    source') or line.startswith('    rule'):
        return DIM
    return TEXT


def render(lines, count):
    img = Image.new('RGB', (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, WIDTH, 48], radius=0, fill=BAR)
    for x, color in ((24, '#ff5f56'), (48, '#ffbd2e'), (72, '#27c93f')):
        draw.ellipse([x, 18, x + 13, 31], fill=color)
    draw.text((100, 13), 'fin-evidence  —  terminal demo', font=load_font(16), fill=DIM)
    font = load_font(19)
    y = PAD_TOP
    for line in lines[:count]:
        draw.text((PAD_X, y), line, font=font, fill=color_for(line))
        y += LINE_H
    draw.text((PAD_X, HEIGHT - 32), 'cn-fin-evidence · 60 datasets · page-level evidence',
              font=load_font(14), fill=DIM)
    return img


def main() -> int:
    env = dict(os.environ)
    env['PYTHONPATH'] = str(ROOT / 'src')
    proc = subprocess.run(
        [sys.executable, '-m', 'fin_evidence.cli', '--data', 'data', 'demo'],
        cwd=str(ROOT), env=env, text=True, capture_output=True, check=True,
    )
    lines = proc.stdout.splitlines()
    OUT.mkdir(parents=True, exist_ok=True)
    final = render(lines, len(lines))
    final.save(OUT / 'demo.png', optimize=True)

    # 逐段出现，最后一帧停留 2 秒；帧数控制在 8 帧以内。
    total = len(lines)
    frames = []
    for i in range(1, total + 1, max(1, total // 7)):
        frames.append(render(lines, i))
        frames[-1] = frames[-1].convert('P', palette=Image.ADAPTIVE, colors=64)
    if len(frames) < 3:
        frames = [render(lines, i).convert('P', palette=Image.ADAPTIVE, colors=64)
                  for i in range(1, total + 1)]
    durations = [90] * (len(frames) - 1) + [2000]
    frames[0].save(OUT / 'demo.gif', save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, optimize=True)
    print(OUT / 'demo.png')
    print(OUT / 'demo.gif')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
