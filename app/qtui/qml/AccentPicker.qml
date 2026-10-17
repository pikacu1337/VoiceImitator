import QtQuick
import QtQuick.Effects

// Выбор акцента, как AccentPicker в ZapretLauncher: квадрат насыщенности и яркости,
// полоса оттенков, восемь готовых цветов 4×2 и поле #RRGGBB. Оттенок хранится отдельно
// от цвета — если провести метку через серый или чёрный, оттенок не теряется.
Item {
    id: p
    property real hue: 0.58
    property real sat: 0.5
    property real val: 1
    property var swatches: []
    signal changed(color color, real hue)
    signal invalid(string text)
    implicitHeight: 104

    readonly property color current: Qt.hsva(hue, sat, val, 1)

    function setColor(c, keepHue) {
        var col = Qt.color(c)
        if (col.hsvHue >= 0 && !keepHue)
            p.hue = col.hsvHue
        p.sat = col.hsvSaturation
        p.val = col.hsvValue
        p.changed(p.current, p.hue)
    }
    function hex(c) { return c.toString().slice(0, 7).toUpperCase() }

    // квадрат насыщенности (слева направо) и яркости (сверху вниз)
    Rectangle {
        id: sv
        x: 0; y: 0
        width: p.width - hueBar.width - 9 - 17 - right.width
        height: 104
        radius: 6
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: "white" }
            GradientStop { position: 1; color: Qt.hsva(p.hue, 1, 1, 1) }
        }
        Rectangle {
            anchors.fill: parent
            radius: 6
            gradient: Gradient {
                GradientStop { position: 0; color: "transparent" }
                GradientStop { position: 1; color: "black" }
            }
        }
        Rectangle {   // метка — белое кольцо с тенью
            width: 12; height: 12; radius: 6
            x: p.sat * sv.width - 6
            y: (1 - p.val) * sv.height - 6
            color: "transparent"
            border.color: "white"
            border.width: 2
            layer.enabled: true
            layer.effect: MultiEffect { shadowEnabled: true; shadowBlur: 0.4; shadowColor: "#e6000000" }
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            function pick(m) {
                p.sat = Math.max(0, Math.min(1, m.x / sv.width))
                p.val = Math.max(0, Math.min(1, 1 - m.y / sv.height))
                p.changed(p.current, p.hue)
            }
            onPressed: (m) => pick(m)
            onPositionChanged: (m) => { if (pressed) pick(m) }
        }
    }

    // полоса оттенков
    Item {
        id: hueBar
        x: sv.width + 9
        width: 20
        height: 104
        Rectangle {
            x: 3; width: 14; height: parent.height; radius: 4
            gradient: Gradient {
                GradientStop { position: 0.000; color: "#ff0000" }
                GradientStop { position: 0.167; color: "#ffff00" }
                GradientStop { position: 0.333; color: "#00ff00" }
                GradientStop { position: 0.500; color: "#00ffff" }
                GradientStop { position: 0.667; color: "#0000ff" }
                GradientStop { position: 0.833; color: "#ff00ff" }
                GradientStop { position: 1.000; color: "#ff0000" }
            }
        }
        Rectangle {
            width: 20; height: 5; radius: 2
            y: p.hue * (hueBar.height - 5)
            color: "white"
            layer.enabled: true
            layer.effect: MultiEffect { shadowEnabled: true; shadowBlur: 0.4; shadowColor: "#e6000000" }
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            function pick(m) {
                p.hue = Math.max(0, Math.min(0.999, m.y / hueBar.height))
                p.changed(p.current, p.hue)
            }
            onPressed: (m) => pick(m)
            onPositionChanged: (m) => { if (pressed) pick(m) }
        }
    }

    // готовые цвета и поле #RRGGBB
    Column {
        id: right
        x: hueBar.x + hueBar.width + 17
        width: 4 * 26 + 3 * 6
        spacing: 8
        Grid {
            columns: 4
            columnSpacing: 6
            rowSpacing: 4
            Repeater {
                model: p.swatches
                delegate: Item {
                    required property string modelData
                    width: 26; height: 26
                    Rectangle {   // кольцо выбранного
                        anchors.fill: parent
                        radius: 13
                        color: "transparent"
                        border.width: 1.5
                        border.color: p.hex(p.current) === modelData.toUpperCase() ? Theme.text
                                      : sw.containsMouse ? Qt.rgba(1, 1, 1, 0.35) : "transparent"
                    }
                    Rectangle { anchors.centerIn: parent; width: 16; height: 16; radius: 8; color: modelData }
                    MouseArea {
                        id: sw
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: p.setColor(modelData, false)
                    }
                }
            }
        }
        Rectangle {
            width: parent.width
            height: 30
            radius: Theme.rPill
            color: Theme.fieldFill
            border.width: 1
            border.color: entry.activeFocus ? Qt.rgba(1, 1, 1, 0.35) : Theme.fieldEdge
            TextInput {
                id: entry
                anchors.fill: parent
                horizontalAlignment: TextInput.AlignHCenter
                verticalAlignment: TextInput.AlignVCenter
                color: Theme.text
                selectionColor: Qt.rgba(1, 1, 1, 0.25)
                font.family: Theme.font
                font.pixelSize: 13
                selectByMouse: true
                text: p.hex(p.current)
                function apply() {
                    var m = /^#?([0-9a-fA-F]{6})$/.exec(text.trim())
                    if (m)
                        p.setColor("#" + m[1], false)
                    else {
                        p.invalid("Цвет пишется как #RRGGBB, например #7AB8FF")
                        text = Qt.binding(() => p.hex(p.current))
                    }
                }
                onAccepted: apply()
                onActiveFocusChanged: if (!activeFocus) apply()
            }
        }
    }
}
