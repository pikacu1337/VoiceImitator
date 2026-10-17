import QtQuick

// Ползунок прямо на стекле: дорожка 4px со скруглёнными концами, метка — вертикальная
// скруглённая плашка 10×13 (под курсором 10×15), пройденная часть — акцент.
Item {
    id: s
    property real from: 0
    property real to: 1
    property real value: 0
    property real stepSize: 0
    signal moved(real value)
    implicitWidth: 170
    implicitHeight: 24
    opacity: enabled ? 1 : 0.4

    readonly property real pad: 7
    readonly property real frac: (value - from) / ((to - from) || 1)
    readonly property real xv: pad + frac * (width - 2 * pad)

    Rectangle {   // дорожка
        x: s.pad - 2; width: s.width - 2 * s.pad + 4
        height: 4; radius: 2
        anchors.verticalCenter: parent.verticalCenter
        color: Theme.trackOff
    }
    Rectangle {   // пройденная часть
        x: s.pad - 2; width: s.xv - s.pad + 4
        height: 4; radius: 2
        anchors.verticalCenter: parent.verticalCenter
        color: Theme.accent
    }
    Rectangle {   // метка
        width: 10
        height: area.containsMouse || area.pressed ? 15 : 13
        radius: 3
        x: s.xv - width / 2
        anchors.verticalCenter: parent.verticalCenter
        color: Theme.accent
        Behavior on height { NumberAnimation { duration: 90 } }
    }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: s.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        enabled: s.enabled
        function pick(mx) {
            var f = Math.max(0, Math.min(1, (mx - s.pad) / Math.max(1, s.width - 2 * s.pad)))
            var v = s.from + f * (s.to - s.from)
            if (s.stepSize > 0)
                v = s.from + Math.round((v - s.from) / s.stepSize) * s.stepSize
            if (v !== s.value) {
                s.value = v
                s.moved(v)
            }
        }
        onPressed: (m) => pick(m.x)
        onPositionChanged: (m) => { if (pressed) pick(m.x) }
    }
}
