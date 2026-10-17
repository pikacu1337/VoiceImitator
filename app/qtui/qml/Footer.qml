import QtQuick

// Строка версии внизу, почти прозрачная. Сообщение проявляется под ней (версия
// поднимается на 10px), через 8 с всё возвращается.
Item {
    id: f
    property string version
    height: 52

    function flash(text) {
        msg.text = text
        hold.restart()
        state = "message"
    }

    Item {
        id: lines
        width: parent.width
        height: parent.height
        Text {
            id: ver
            y: (f.height - height) / 2
            text: "VoiceImitator " + f.version
            color: Theme.text
            opacity: 0.30
            font.family: Theme.font
            font.pixelSize: 12
        }
        Text {
            id: msg
            y: ver.y + 19
            width: f.width
            elide: Text.ElideRight
            color: Theme.muted
            opacity: 0
            font.family: Theme.font
            font.pixelSize: 12
        }
    }
    Timer { id: hold; interval: 8000; onTriggered: f.state = "" }

    states: State {
        name: "message"
        PropertyChanges { lines.y: -10; msg.opacity: 1 }
    }
    transitions: [
        Transition { to: "message"; NumberAnimation { properties: "y,opacity"; duration: 280; easing.type: Easing.OutCubic } },
        Transition { to: ""; NumberAnimation { properties: "y,opacity"; duration: 220; easing.type: Easing.OutCubic } }
    ]
}
