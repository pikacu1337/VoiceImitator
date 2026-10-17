pragma Singleton
import QtQuick

// Токены Night Glass (из app/theme.py). Полупрозрачные — как в оригинале: стекло рисует
// видеокарта, поэтому здесь не нужно сводить их в сплошные цвета.
QtObject {
    // меняются из окна
    property color accent: "#7ab8ff"
    property Item frost: null            // размытый фон — из него вырезается стекло панелей

    readonly property color accentSoft: Qt.rgba(accent.r * 0.64, accent.g * 0.64, accent.b * 0.64, 1)

    readonly property color window: "#050505"
    readonly property color text: "#f2f2f2"
    readonly property color muted: "#9a9a9a"
    readonly property color faint: "#6b6b6b"

    readonly property color edge: Qt.rgba(1, 1, 1, 0x24 / 255)          // обводка стекла и кнопок
    readonly property color fieldFill: Qt.rgba(0, 0, 0, 0.16)            // поле — стекло плотнее
    readonly property color fieldEdge: Qt.rgba(1, 1, 1, 0.09)
    readonly property color fieldHover: Qt.rgba(1, 1, 1, 0.04)
    readonly property color trackOff: Qt.rgba(1, 1, 1, 0x1f / 255)
    readonly property color wash: Qt.rgba(1, 1, 1, 0x1a / 255)          // подсветка под курсором
    readonly property color popup: "#191919"
    readonly property color popupWash: "#262626"

    readonly property color solid: "#dedede"
    readonly property color solidHover: "#ffffff"
    readonly property color solidText: "#0a0a0a"
    readonly property color knob: "#eaeaea"

    readonly property real glassDim: 0.28
    readonly property real veil: 0.07

    readonly property int rBar: 2
    readonly property int rRow: 8
    readonly property int rPill: 9
    readonly property int rCard: 16

    readonly property string font: "Segoe UI Variable Text"
    readonly property string glyphs: "Segoe MDL2 Assets"

    readonly property int pad: 24        // поля окна
    readonly property int gap: 14        // между панелями
    readonly property int maxWidth: 1320 // как MaxWidth у настроек лаунчера
}
