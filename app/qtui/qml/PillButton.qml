import QtQuick

// Кнопка-пилюля со значком прямо на фоне, как «i Информация» в ZapretLauncher:
// под ней своё стекло, обводка, под курсором — подсветка и обводка ярче.
Item {
    id: b
    property string glyph
    property alias text: label.text
    signal clicked()
    implicitWidth: row.implicitWidth + 32
    implicitHeight: row.implicitHeight + 16

    Glass { anchors.fill: parent; radius: Theme.rPill }
    Rectangle {
        anchors.fill: parent
        radius: Theme.rPill
        color: area.containsMouse ? Qt.rgba(1, 1, 1, 0x1a / 255) : "transparent"
        border.width: 1
        border.color: area.containsMouse ? Qt.rgba(1, 1, 1, 0x52 / 255) : Theme.edge
        Behavior on color { ColorAnimation { duration: 120 } }
    }
    Row {
        id: row
        anchors.centerIn: parent
        spacing: 9
        Text {
            text: b.glyph
            color: Theme.text
            font.family: Theme.glyphs
            font.pixelSize: 14
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: 1
        }
        Text {
            id: label
            color: Theme.text
            font.family: Theme.font
            font.pointSize: 13.5 * 0.75
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: b.clicked()
    }
}
