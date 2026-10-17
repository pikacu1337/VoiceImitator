import QtQuick
import QtQuick.Controls.Basic

// Выпадающий список: поле из плотного стекла, тонкий шеврон Segoe MDL2, список — тёмная пилюля.
ComboBox {
    id: box
    property string placeholder: ""     // показывать вместо выбранного (меню пресетов)
    signal picked(string value)
    implicitHeight: 34
    font.family: Theme.font
    font.pixelSize: 13
    displayText: placeholder || currentText
    onActivated: (i) => box.picked(box.textAt(i))

    background: Rectangle {
        radius: Theme.rPill
        color: box.hovered ? Qt.rgba(1, 1, 1, 0.04) : Theme.fieldFill
        border.width: 1
        border.color: Theme.fieldEdge
    }
    contentItem: Text {
        leftPadding: 10
        rightPadding: 30
        text: box.displayText
        color: Theme.text
        font: box.font
        elide: Text.ElideRight
        verticalAlignment: Text.AlignVCenter
    }
    indicator: Text {
        x: box.width - width - 13
        anchors.verticalCenter: box.verticalCenter
        anchors.verticalCenterOffset: 1
        text: ""
        color: box.hovered ? Theme.text : Theme.muted
        font.family: Theme.glyphs
        font.pixelSize: 10
    }
    delegate: ItemDelegate {
        id: item
        required property int index
        required property var modelData
        width: ListView.view ? ListView.view.width : box.width
        height: 30
        contentItem: Text {
            leftPadding: 4
            text: item.modelData
            color: Theme.text
            font: box.font
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: 6
            color: item.hovered ? Theme.popupWash : "transparent"
        }
    }
    popup: Popup {
        y: box.height + 4
        width: box.width
        padding: 4
        implicitHeight: Math.min(contentItem.implicitHeight + 8, 320)
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: box.popup.visible ? box.delegateModel : null
            currentIndex: box.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator {}
        }
        background: Rectangle {
            radius: Theme.rPill
            color: Theme.popup
            border.width: 1
            border.color: Theme.edge
        }
    }
}
