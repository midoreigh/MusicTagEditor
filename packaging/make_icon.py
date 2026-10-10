"""Render packaging/icon.png (1024px). Run once: uv run python packaging/make_icon.py"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QGuiApplication, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen)

S = 1024
app = QGuiApplication(sys.argv)
img = QImage(S, S, QImage.Format.Format_ARGB32)
img.fill(Qt.GlobalColor.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.RenderHint.Antialiasing)

# rounded-square background
grad = QLinearGradient(0, 0, S, S)
grad.setColorAt(0, QColor("#ff7a45"))
grad.setColorAt(1, QColor("#c2185b"))
bg = QPainterPath()
bg.addRoundedRect(QRectF(64, 64, S - 128, S - 128), 200, 200)
p.fillPath(bg, QBrush(grad))

# luggage-tag shape
tag = QPainterPath()
tag.moveTo(QPointF(300, 250))
tag.lineTo(QPointF(640, 250))
tag.lineTo(QPointF(800, 410))
tag.lineTo(QPointF(800, 770))
tag.quadTo(QPointF(800, 800), QPointF(770, 800))
tag.lineTo(QPointF(330, 800))
tag.quadTo(QPointF(300, 800), QPointF(300, 770))
tag.closeSubpath()
p.fillPath(tag, QColor(255, 255, 255, 240))
p.setPen(Qt.PenStyle.NoPen)
p.setBrush(QColor("#c2185b"))
p.drawEllipse(QPointF(650, 380), 34, 34)

# raw "lines" of tag data
p.setPen(QPen(QColor("#e8577a"), 30, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
for i, w in enumerate((300, 380, 250)):
    y = 520 + i * 80
    p.drawLine(QPointF(370, y), QPointF(370 + w, y))

# music note
f = QFont()
f.setPixelSize(300)
f.setBold(True)
p.setFont(f)
p.setPen(QColor("#ff7a45"))
p.drawText(QRectF(520, 530, 300, 300), Qt.AlignmentFlag.AlignCenter, "♪")
p.end()

out = Path(__file__).with_name("icon.png")
img.save(str(out))
print("wrote", out)
