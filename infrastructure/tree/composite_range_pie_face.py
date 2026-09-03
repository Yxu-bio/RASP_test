from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QColor, QBrush, QPainter, QPainterPath, QPen, QPolygonF
from PyQt5.QtWidgets import QGraphicsRectItem

from ete3 import faces


class _CompositeRangePieItem(QGraphicsRectItem):
    def __init__(self, percents, width, height, color_patterns, line_color=None):
        super().__init__(0, 0, width, height)
        self.percents = [float(value or 0.0) for value in list(percents or [])]
        self.color_patterns = [list(colors or []) for colors in list(color_patterns or [])]
        self.line_color = line_color

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing, True)
        angle_start = 0.0
        for index, percent in enumerate(self.percents):
            angle_span = max(0.0, percent) * 3.6
            if angle_span <= 0.0:
                continue
            path = self._wedge_path(angle_start, angle_span)
            colors = self.color_patterns[index] if index < len(self.color_patterns) else []
            colors = [color for color in colors if QColor(str(color)).isValid()] or ["#808080"]
            if len(colors) == 1:
                painter.fillPath(path, QBrush(QColor(colors[0])))
            else:
                self._paint_stripes(painter, path, colors)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#ffffff"), 0.6))
            painter.drawPath(path)
            angle_start += angle_span

        if self.line_color:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(self.line_color), 1.2))
            painter.drawEllipse(self.rect())

    def _wedge_path(self, start_degrees, span_degrees):
        rect = self.rect()
        center = rect.center()
        path = QPainterPath(center)
        path.arcTo(rect, start_degrees, span_degrees)
        path.closeSubpath()
        return path

    def _paint_stripes(self, painter, path, colors):
        rect = self.rect()
        stripe_width = max(2.0, min(rect.width(), rect.height()) / 6.0)
        painter.save()
        painter.setClipPath(path)
        painter.setPen(Qt.NoPen)
        position = -rect.height()
        stripe_index = 0
        while position < rect.width():
            polygon = QPolygonF(
                [
                    QPointF(position, rect.top()),
                    QPointF(position + stripe_width, rect.top()),
                    QPointF(position + stripe_width + rect.height(), rect.bottom()),
                    QPointF(position + rect.height(), rect.bottom()),
                ]
            )
            painter.setBrush(QBrush(QColor(colors[stripe_index % len(colors)])))
            painter.drawPolygon(polygon)
            position += stripe_width
            stripe_index += 1
        painter.restore()


class CompositeRangePieFace(faces.StaticItemFace):
    def __init__(self, percents, width, height, color_patterns, line_color=None):
        total = sum(float(value or 0.0) for value in list(percents or []))
        if round(total) > 100:
            raise ValueError("CompositeRangePieFace: percentage values > 100")
        item = _CompositeRangePieItem(
            percents=percents,
            width=width,
            height=height,
            color_patterns=color_patterns,
            line_color=line_color,
        )
        super().__init__(item)
