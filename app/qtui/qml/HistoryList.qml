import QtQuick
import QtQuick.Controls.Basic

// История фраз: поле из плотного стекла, строки 28px, под курсором — подсветка.
// Клик повторяет фразу; порядок строк меняет только новая фраза из поля ввода.
Rectangle {
    id: box
    property var items: []
    signal picked(string text)
    implicitHeight: 6 * 2 + 7 * 30
    radius: Theme.rRow
    color: Theme.fieldFill
    border.width: 1
    border.color: Theme.fieldEdge

    ListView {
        id: list
        anchors.fill: parent
        anchors.margins: 6
        clip: true
        spacing: 2
        model: box.items
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {
            id: bar
            width: 6
            policy: list.contentHeight > list.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
            contentItem: Rectangle { radius: 3; color: Qt.rgba(1, 1, 1, bar.pressed ? 0.26 : 0.16) }
            background: Item {}
        }
        delegate: Rectangle {
            id: row
            required property string modelData
            width: list.width - (bar.visible ? 12 : 0)
            height: 28
            radius: Theme.rRow
            color: area.containsMouse ? Qt.rgba(1, 1, 1, 0.07) : "transparent"
            Text {
                anchors.fill: parent
                anchors.leftMargin: 11
                anchors.rightMargin: 11
                verticalAlignment: Text.AlignVCenter
                text: row.modelData.replace(/\n/g, " ")
                elide: Text.ElideRight
                color: area.containsMouse ? Theme.text : Theme.muted
                font.family: Theme.font
                font.pixelSize: 13
            }
            MouseArea {
                id: area
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: box.picked(row.modelData)
            }
        }
    }
}
