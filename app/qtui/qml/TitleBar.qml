import QtQuick
import QtQuick.Window

// Полоса 44px вместо системного заголовка: вкладки по центру, кнопки окна справа.
// Пустое место тянет окно (системно — с Aero Snap), двойной щелчок разворачивает.
// Под открытой вкладкой — чёрточка-акцент 18×3: переезжает за 0.36 с (CubicInOut).
Item {
    id: bar
    property var tabs: []
    property int current: 0
    property bool showTabs: true
    signal select(int index)
    height: 44

    MouseArea {
        anchors.fill: parent
        onPressed: Window.window.startSystemMove()
        onDoubleClicked: toggleMax()
    }
    function toggleMax() {
        var w = Window.window
        if (w.visibility === Window.Maximized) w.showNormal()
        else w.showMaximized()
    }

    Row {
        id: tabRow
        visible: bar.showTabs
        anchors.horizontalCenter: parent.horizontalCenter
        height: parent.height
        Repeater {
            id: rep
            model: bar.tabs
            delegate: Item {
                id: tab
                required property int index
                required property string modelData
                width: label.implicitWidth + 40
                height: bar.height
                Text {
                    id: label
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: 9 + 3
                    text: tab.modelData
                    color: tab.index === bar.current || area.containsMouse ? Theme.text : Theme.muted
                    font.family: Theme.font
                    font.pointSize: 13.5 * 0.75
                    Behavior on color { ColorAnimation { duration: 120 } }
                }
                MouseArea {
                    id: area
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: bar.select(tab.index)
                }
            }
        }
    }
    Rectangle {
        id: underline
        visible: bar.showTabs
        width: 18; height: 3; radius: Theme.rBar
        y: bar.height - 4 - height
        color: Theme.accent
        opacity: 0
        property Item target: rep.count > bar.current ? rep.itemAt(bar.current) : null
        x: target ? tabRow.x + target.x + (target.width - width) / 2 : 0
        Behavior on x { enabled: underline.opacity > 0; NumberAnimation { duration: 360; easing.type: Easing.InOutCubic } }
        Component.onCompleted: fadeIn.start()
        NumberAnimation on opacity { id: fadeIn; running: false; to: 1; duration: 350; easing.type: Easing.OutCubic }
    }

    component WinButton: Rectangle {
        id: wb
        property string glyph
        signal clicked()
        width: 36; height: 30; radius: 8
        color: wa.containsMouse ? Qt.rgba(1, 1, 1, 0x1f / 255) : "transparent"
        Text {
            anchors.centerIn: parent
            text: wb.glyph
            color: wa.containsMouse ? Theme.text : Theme.muted
            font.family: Theme.glyphs
            font.pixelSize: 10
        }
        MouseArea { id: wa; anchors.fill: parent; hoverEnabled: true; onClicked: wb.clicked() }
    }
    Row {
        anchors.right: parent.right
        anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        WinButton { glyph: ""; onClicked: Window.window.showMinimized() }
        WinButton {
            glyph: Window.window && Window.window.visibility === Window.Maximized ? "" : ""
            onClicked: bar.toggleMax()
        }
        WinButton { glyph: ""; onClicked: Window.window.close() }
    }
}
