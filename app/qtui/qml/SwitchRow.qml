import QtQuick

// Переключатель 40×22 и подпись справа; включённый — приглушённый акцент.
Row {
    id: row
    property bool checked: false
    property string text: "Включено"
    signal toggled(bool checked)
    spacing: 10

    function toggle() {
        row.checked = !row.checked
        row.toggled(row.checked)
    }

    Rectangle {
        width: 40; height: 22; radius: 11
        color: row.checked ? Theme.accentSoft : Qt.rgba(1, 1, 1, 0.13)
        Behavior on color { ColorAnimation { duration: 150 } }
        Rectangle {
            width: 16; height: 16; radius: 8
            y: 3
            x: row.checked ? 21 : 3
            color: Theme.knob
            Behavior on x { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
        }
        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: row.toggle() }
    }
    Text {
        text: row.text
        color: label.containsMouse ? Theme.text : Theme.muted
        font.family: Theme.font
        font.pixelSize: 13
        anchors.verticalCenter: parent.verticalCenter
        MouseArea { id: label; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: row.toggle() }
    }
}
