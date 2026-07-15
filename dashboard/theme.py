"""
Centralized professional dashboard theme.
"""


def dashboard_stylesheet() -> str:
    return """
        QMainWindow, QWidget {
            background: #101418;
            color: #e8edf2;
            font-family: Segoe UI, Arial, sans-serif;
            font-size: 13px;
        }
        QStatusBar {
            background: #0b0f13;
            color: #9aa7b4;
            border-top: 1px solid #222b35;
        }
        QWidget#ApplicationHeader {
            background: #151b21;
            border: 1px solid #27313c;
            border-radius: 8px;
        }
        QLabel#HeaderTitle {
            color: #f4f7fa;
            font-size: 22px;
            font-weight: 700;
        }
        QLabel#HeaderSubtitle {
            color: #9aa7b4;
        }
        QGroupBox {
            background: #151b21;
            border: 1px solid #27313c;
            border-radius: 8px;
            margin-top: 22px;
            padding: 14px 12px 12px 12px;
            font-weight: 650;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 8px;
            color: #d8dee6;
        }
        QSplitter::handle {
            background: #101418;
            width: 8px;
        }
        QTabWidget::pane {
            border: 1px solid #27313c;
            background: #101418;
            border-radius: 8px;
            top: -1px;
        }
        QTabBar::tab {
            background: #151b21;
            color: #9aa7b4;
            border: 1px solid #27313c;
            border-bottom: none;
            padding: 10px 20px;
            min-width: 120px;
        }
        QTabBar::tab:selected {
            background: #1d252d;
            color: #ffffff;
            border-top: 2px solid #5aa9e6;
        }
        QTabBar::tab:hover {
            color: #ffffff;
        }
        QLabel[role="field-name"], QLabel[role="metric-title"] {
            color: #8f9ba8;
            font-size: 12px;
            font-weight: 500;
        }
        QLabel[role="field-value"], QLabel[role="metric-value"] {
            color: #e8edf2;
            font-weight: 600;
        }
        QLabel[role="metric-value"] {
            font-size: 20px;
        }
        QFrame[role="metric-card"] {
            background: #10161c;
            border: 1px solid #27313c;
            border-radius: 8px;
        }
        QLabel[role="status-badge"] {
            border-radius: 8px;
            padding: 4px 10px;
            font-weight: 700;
        }
        QLabel[status="positive"] {
            color: #7ee2a8;
            background: rgba(36, 146, 92, 0.16);
            border: 1px solid rgba(126, 226, 168, 0.28);
        }
        QLabel[status="neutral"] {
            color: #c8d1dc;
            background: rgba(143, 155, 168, 0.12);
            border: 1px solid rgba(143, 155, 168, 0.24);
        }
        QLabel[status="warning"] {
            color: #ffd166;
            background: rgba(255, 209, 102, 0.14);
            border: 1px solid rgba(255, 209, 102, 0.26);
        }
        QLabel[status="negative"] {
            color: #ff8b8b;
            background: rgba(218, 71, 71, 0.15);
            border: 1px solid rgba(255, 139, 139, 0.26);
        }
        QTableWidget {
            background: #10161c;
            alternate-background-color: #131b22;
            border: 1px solid #27313c;
            border-radius: 6px;
            gridline-color: #27313c;
            selection-background-color: #1f5f8b;
            selection-color: #ffffff;
        }
        QHeaderView::section {
            background: #1d252d;
            color: #c8d1dc;
            border: none;
            border-right: 1px solid #27313c;
            padding: 6px 8px;
            font-weight: 650;
        }
    """
