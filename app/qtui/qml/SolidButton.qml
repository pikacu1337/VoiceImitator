import QtQuick

// Сплошная «главная» кнопка: светлая пилюля, под курсором — белая.
Rectangle {
    id: b
    property alias text: label.text
    property bool enabled: true
    signal clicked()
    implicitWidth: 140
    implicitHeight: 38
    radius: Theme.rPill
    color: b.enabled && area.containsMouse ? Theme.solidHover : Theme.solid
    Behavior on color { ColorAnimation { duration: 120 } }

    Text {
        id: label
        anchors.centerIn: parent
        color: b.enabled ? Theme.solidText : "#5a5a5a"
        font.family: Theme.font
        font.pixelSize: 13
    }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: b.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: if (b.enabled) b.clicked()
    }
}
