import QtQuick

// Прозрачная кнопка с обводкой; выбранная (selected) — обводка цветом акцента.
Rectangle {
    id: b
    property alias text: label.text
    property bool selected: false
    property bool dim: false            // текст приглушён (невыбранный сегмент)
    signal clicked()
    implicitWidth: 110
    implicitHeight: 34
    radius: Theme.rPill
    color: area.containsMouse ? Qt.rgba(1, 1, 1, 0.10) : "transparent"
    border.width: 1
    border.color: b.selected ? Theme.accent : Qt.rgba(1, 1, 1, 0.16)
    Behavior on color { ColorAnimation { duration: 120 } }

    Text {
        id: label
        anchors.centerIn: parent
        width: Math.min(implicitWidth, b.width - 16)
        elide: Text.ElideRight
        color: b.dim && !area.containsMouse ? Theme.muted : Theme.text
        font.family: Theme.font
        font.pixelSize: 13
    }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: b.clicked()
    }
}
