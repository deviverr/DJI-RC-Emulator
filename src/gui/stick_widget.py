"""
Custom Qt widgets for visualizing stick positions and expo curves.
Supports real-time updates, deadzone ring, and movement trail.
"""
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QRadialGradient
from PySide6.QtWidgets import QWidget, QSizePolicy


class StickWidget(QWidget):
    """
    Draws a square area with crosshairs and a dot indicating stick position.
    Position is set via set_position(x, y) with normalized values (-1.0 to +1.0).
    Features: deadzone ring, movement trail, glow effect.
    """

    def __init__(self, label: str = "Stick", parent=None):
        super().__init__(parent)
        self._x = 0.0  # -1.0 to +1.0
        self._y = 0.0  # -1.0 to +1.0
        self._label = label

        # Deadzone visualization
        self._deadzone = 0.02

        # Movement trail
        self._trail: list[tuple[float, float]] = []
        self._max_trail = 15

        self.setMinimumSize(160, 160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Colors
        self._bg_color = QColor(30, 30, 35)
        self._border_color = QColor(70, 70, 80)
        self._cross_color = QColor(50, 50, 60)
        self._dot_color = QColor(0, 180, 255)
        self._dot_glow = QColor(0, 120, 220, 80)
        self._trail_color = QColor(0, 180, 255)
        self._text_color = QColor(160, 160, 170)
        self._value_color = QColor(220, 220, 230)
        self._dz_fill = QColor(255, 180, 0, 30)
        self._dz_border = QColor(255, 180, 0, 80)

    def set_position(self, x: float, y: float):
        """Set stick position. x,y in range -1.0 to +1.0. Triggers repaint."""
        self._x = max(-1.0, min(1.0, x))
        self._y = max(-1.0, min(1.0, y))
        self._trail.append((self._x, self._y))
        if len(self._trail) > self._max_trail:
            self._trail.pop(0)
        self.update()

    def set_label(self, label: str):
        self._label = label
        self.update()

    def set_deadzone(self, dz: float):
        """Set deadzone radius for visualization (0.0 to 1.0)."""
        self._deadzone = max(0.0, min(1.0, dz))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Square area with padding for labels
        pad_top = 22
        pad_bottom = 20
        pad_side = 10
        available_w = w - 2 * pad_side
        available_h = h - pad_top - pad_bottom
        size = min(available_w, available_h)

        # Center the square
        cx = w / 2
        cy = pad_top + available_h / 2
        half = size / 2
        move_range = half - 8  # dot movement range within the square

        area = QRectF(cx - half, cy - half, size, size)

        # Background
        painter.fillRect(self.rect(), QColor(25, 25, 30))

        # Square background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._bg_color))
        painter.drawRoundedRect(area, 6, 6)

        # Border
        painter.setPen(QPen(self._border_color, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(area, 6, 6)

        # Crosshairs
        pen = QPen(self._cross_color, 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(QPointF(area.left(), cy), QPointF(area.right(), cy))
        painter.drawLine(QPointF(cx, area.top()), QPointF(cx, area.bottom()))

        # Circle guides (25%, 50%, 75%)
        painter.setPen(QPen(self._cross_color, 0.5, Qt.PenStyle.DotLine))
        for frac in [0.25, 0.5, 0.75]:
            r = half * frac
            painter.drawEllipse(QPointF(cx, cy), r, r)

        # Deadzone ring
        if self._deadzone > 0.005:
            dz_radius = self._deadzone * move_range
            painter.setPen(QPen(self._dz_border, 1, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(self._dz_fill))
            painter.drawEllipse(QPointF(cx, cy), dz_radius, dz_radius)
            painter.setBrush(Qt.BrushStyle.NoBrush)

        # Movement trail (fading dots)
        if len(self._trail) > 1:
            for i, (tx, ty) in enumerate(self._trail[:-1]):
                alpha = int(120 * (i + 1) / len(self._trail))
                trail_size = 2 + (i / len(self._trail)) * 2
                trail_color = QColor(0, 180, 255, alpha)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(trail_color))
                px = cx + tx * move_range
                py = cy - ty * move_range
                painter.drawEllipse(QPointF(px, py), trail_size, trail_size)

        # Dot position (map -1..+1 to pixel coords)
        dot_x = cx + self._x * move_range
        dot_y = cy - self._y * move_range  # Y inverted: up = positive

        # Glow effect
        glow_radius = 18
        gradient = QRadialGradient(QPointF(dot_x, dot_y), glow_radius)
        gradient.setColorAt(0, self._dot_glow)
        gradient.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(dot_x, dot_y), glow_radius, glow_radius)

        # Line from center to dot
        painter.setPen(QPen(QColor(0, 180, 255, 30), 2))
        painter.drawLine(QPointF(cx, cy), QPointF(dot_x, dot_y))

        # Dot
        dot_radius = 7
        painter.setPen(QPen(self._dot_color.darker(120), 1.5))
        painter.setBrush(QBrush(self._dot_color))
        painter.drawEllipse(QPointF(dot_x, dot_y), dot_radius, dot_radius)

        # Inner highlight
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 60)))
        painter.drawEllipse(QPointF(dot_x - 2, dot_y - 2), 3, 3)

        # Label
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(self._text_color)
        painter.drawText(QRectF(0, 2, w, pad_top), Qt.AlignmentFlag.AlignCenter, self._label)

        # Values
        font_small = QFont("Consolas", 8)
        painter.setFont(font_small)
        painter.setPen(self._value_color)
        val_text = f"X:{self._x:+.2f}  Y:{self._y:+.2f}"
        painter.drawText(
            QRectF(0, h - pad_bottom, w, pad_bottom),
            Qt.AlignmentFlag.AlignCenter, val_text
        )

        painter.end()


class ExpoPreviewWidget(QWidget):
    """
    Small widget that draws an expo/rate curve preview.
    Shows how expo affects the input->output response.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expo = 0.0
        self._rate = 1.0
        self.setMinimumSize(120, 120)
        self.setMaximumSize(200, 200)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_curve(self, expo: float, rate: float):
        self._expo = max(0.0, min(1.0, expo))
        self._rate = max(0.1, min(1.0, rate))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        pad = 10

        area = QRectF(pad, pad, w - 2 * pad, h - 2 * pad)

        # Background
        painter.fillRect(self.rect(), QColor(30, 30, 35))
        painter.setPen(QPen(QColor(60, 60, 70), 1))
        painter.drawRect(area)

        # Grid
        painter.setPen(QPen(QColor(45, 45, 55), 0.5, Qt.PenStyle.DotLine))
        mid_x = area.left() + area.width() / 2
        mid_y = area.top() + area.height() / 2
        painter.drawLine(QPointF(mid_x, area.top()), QPointF(mid_x, area.bottom()))
        painter.drawLine(QPointF(area.left(), mid_y), QPointF(area.right(), mid_y))

        # Linear reference line (gray)
        painter.setPen(QPen(QColor(80, 80, 90), 1, Qt.PenStyle.DashLine))
        painter.drawLine(
            QPointF(area.left(), area.bottom()),
            QPointF(area.right(), area.top())
        )

        # Expo curve
        painter.setPen(QPen(QColor(0, 180, 255), 2))
        steps = 60
        points = []
        for i in range(steps + 1):
            input_val = i / steps  # 0 to 1
            expo_val = input_val * (self._expo * input_val * input_val + (1.0 - self._expo))
            output = min(1.0, expo_val * self._rate)
            px = area.left() + input_val * area.width()
            py = area.bottom() - output * area.height()
            points.append(QPointF(px, py))

        for i in range(len(points) - 1):
            painter.drawLine(points[i], points[i + 1])

        painter.end()
